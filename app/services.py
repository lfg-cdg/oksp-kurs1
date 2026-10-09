"""Операции сервиса. Используются и программным интерфейсом, и страницами."""
from datetime import date, timedelta
from typing import Optional

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session
from werkzeug.security import check_password_hash

from . import rules
from .models import Book, Copy, Librarian, Loan, Reader

LOAN_STATUSES = ("active", "overdue", "returned", "on_hand")


class ServiceError(Exception):
    status = 400

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


class NotFound(ServiceError):
    status = 404


class Conflict(ServiceError):
    status = 409


class Invalid(ServiceError):
    status = 422


# ---------- проверка параметров ----------

def parse_int(value, name: str, default: Optional[int] = None,
              minimum: Optional[int] = None, maximum: Optional[int] = None) -> int:
    if value is None or value == "":
        if default is None:
            raise Invalid("invalid_param", f"Параметр {name} обязателен")
        return default
    try:
        number = int(value)
    except (TypeError, ValueError):
        raise Invalid("invalid_param", f"Параметр {name} должен быть целым числом")
    if (minimum is not None and number < minimum) or (maximum is not None and number > maximum):
        raise Invalid("invalid_param", f"Параметр {name} вне допустимого диапазона")
    return number


def parse_paging(args) -> tuple[int, int]:
    page = parse_int(args.get("page"), "page", default=1, minimum=1)
    size = parse_int(args.get("size"), "size", default=20, minimum=1, maximum=100)
    return page, size


def parse_date(value, name: str, default: date) -> date:
    if value is None or value == "":
        return default
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        raise Invalid("invalid_param", f"Параметр {name} должен быть датой ГГГГ-ММ-ДД")


# ---------- представление записей ----------

def reader_short(reader: Reader) -> dict:
    return {"id": reader.id, "full_name": reader.full_name, "card_number": reader.card_number}


def book_short(book: Book) -> dict:
    return {"id": book.id, "title": book.title, "author": book.author}


def loan_to_dict(loan: Loan, today: date) -> dict:
    return {
        "id": loan.id,
        "issued_at": loan.issued_at.isoformat(),
        "due_at": loan.due_at.isoformat(),
        "returned_at": loan.returned_at.isoformat() if loan.returned_at else None,
        "status": rules.loan_status(loan.due_at, loan.returned_at, today),
        "overdue_days": rules.overdue_days(loan.due_at, loan.returned_at, today),
        "fine": str(loan.fine if loan.returned_at else rules.fine_for(loan.due_at, None, today)),
        "reader": reader_short(loan.reader),
        "copy": {"id": loan.copy.id, "inventory_number": loan.copy.inventory_number},
        "book": book_short(loan.copy.book),
    }


# ---------- авторизация ----------

def authenticate(session: Session, login: str, password: str) -> Librarian:
    user = session.scalar(select(Librarian).where(Librarian.login == login))
    if user is None or not check_password_hash(user.password_hash, password):
        raise ServiceError("bad_credentials", "Неверный логин или пароль")
    return user


# ---------- выдачи ----------

def _status_filter(stmt, status: Optional[str], today: date):
    if status == "returned":
        return stmt.where(Loan.returned_at.is_not(None))
    if status == "on_hand":
        return stmt.where(Loan.returned_at.is_(None))
    if status == "active":
        return stmt.where(Loan.returned_at.is_(None), Loan.due_at >= today)
    if status == "overdue":
        return stmt.where(Loan.returned_at.is_(None), Loan.due_at < today)
    return stmt


def list_loans(session: Session, today: date, page: int, size: int,
               status: Optional[str] = None, q: Optional[str] = None,
               reader_id: Optional[int] = None) -> dict:
    if status and status not in LOAN_STATUSES:
        raise Invalid("invalid_param", "Параметр status: active, overdue, returned или on_hand")

    stmt = _status_filter(select(Loan), status, today)
    if reader_id is not None:
        stmt = stmt.where(Loan.reader_id == reader_id)
    if q:
        pattern = f"%{q}%"
        stmt = (stmt.join(Loan.reader).join(Loan.copy).join(Copy.book)
                .where(or_(Reader.full_name.ilike(pattern), Book.title.ilike(pattern))))

    total = session.scalar(select(func.count()).select_from(stmt.subquery()))
    loans = session.scalars(
        stmt.order_by(Loan.issued_at.desc(), Loan.id.desc())
        .offset((page - 1) * size).limit(size)
    ).all()
    return {
        "items": [loan_to_dict(loan, today) for loan in loans],
        "total": total,
        "page": page,
        "size": size,
    }


def get_loan(session: Session, today: date, loan_id: int) -> dict:
    loan = session.get(Loan, loan_id)
    if loan is None:
        raise NotFound("loan_not_found", "Выдача не найдена")
    data = loan_to_dict(loan, today)
    reader = loan.reader
    book = loan.copy.book
    data["reader"].update({"email": reader.email, "phone": reader.phone})
    data["book"].update({"year": book.year, "isbn": book.isbn})
    data["copy"]["shelf"] = loan.copy.shelf
    # Что ещё на руках у этого читателя.
    data["reader_on_hand"] = [
        loan_to_dict(other, today)
        for other in reader.loans
        if other.returned_at is None and other.id != loan.id
    ]
    return data


def _reader_state(reader: Reader, today: date) -> rules.ReaderState:
    on_hand = [loan for loan in reader.loans if loan.returned_at is None]
    overdue = [loan for loan in on_hand if loan.due_at < today]
    return rules.ReaderState(active_loans=len(on_hand), overdue_loans=len(overdue))


def create_loan(session: Session, today: date, reader_id: int, copy_id: int,
                days: int = rules.LOAN_DAYS) -> dict:
    if not 1 <= days <= rules.MAX_LOAN_DAYS:
        raise Invalid("invalid_param", f"Срок выдачи — от 1 до {rules.MAX_LOAN_DAYS} дней")
    # Блокируем строку экземпляра, чтобы две одновременные выдачи не прошли обе.
    copy = session.scalar(select(Copy).where(Copy.id == copy_id).with_for_update())
    if copy is None:
        raise NotFound("copy_not_found", "Экземпляр не найден")
    reader = session.get(Reader, reader_id)
    if reader is None:
        raise NotFound("reader_not_found", "Читатель не найден")

    busy = session.scalar(
        select(func.count()).select_from(Loan)
        .where(Loan.copy_id == copy_id, Loan.returned_at.is_(None))
    )
    try:
        rules.check_issue(copy_is_free=(busy == 0), reader=_reader_state(reader, today))
    except rules.IssueRejected as exc:
        session.rollback()
        raise Conflict(exc.code, exc.message)

    loan = Loan(copy=copy, reader=reader, issued_at=today,
                due_at=today + timedelta(days=days))
    session.add(loan)
    session.commit()
    return loan_to_dict(loan, today)


def return_loan(session: Session, today: date, loan_id: int,
                returned_at: Optional[date] = None) -> dict:
    loan = session.scalar(select(Loan).where(Loan.id == loan_id).with_for_update())
    if loan is None:
        raise NotFound("loan_not_found", "Выдача не найдена")
    if loan.returned_at is not None:
        session.rollback()
        raise Conflict("already_returned", "Экземпляр по этой выдаче уже возвращён")
    returned_at = returned_at or today
    if returned_at < loan.issued_at or returned_at > today:
        session.rollback()
        raise Invalid("invalid_param", "Дата возврата должна быть между датой выдачи и сегодняшним днём")
    loan.returned_at = returned_at
    loan.fine = rules.fine_for(loan.due_at, returned_at, today)
    session.commit()
    return loan_to_dict(loan, today)


# ---------- читатели ----------

def list_readers(session: Session, page: int, size: int, q: Optional[str] = None) -> dict:
    stmt = select(Reader)
    if q:
        pattern = f"%{q}%"
        stmt = stmt.where(or_(Reader.full_name.ilike(pattern), Reader.card_number.ilike(pattern)))
    total = session.scalar(select(func.count()).select_from(stmt.subquery()))
    readers = session.scalars(stmt.order_by(Reader.full_name, Reader.id)
                              .offset((page - 1) * size).limit(size)).all()
    return {
        "items": [dict(reader_short(r), email=r.email) for r in readers],
        "total": total, "page": page, "size": size,
    }


def get_reader(session: Session, today: date, reader_id: int) -> dict:
    reader = session.get(Reader, reader_id)
    if reader is None:
        raise NotFound("reader_not_found", "Читатель не найден")
    loans = sorted(reader.loans, key=lambda l: (l.issued_at, l.id), reverse=True)
    history = [loan_to_dict(loan, today) for loan in loans]
    state = _reader_state(reader, today)
    fines_paid = sum((l.fine or 0) for l in loans if l.returned_at is not None)
    fines_accrued = sum(rules.fine_for(l.due_at, None, today) for l in loans if l.returned_at is None)
    return {
        **reader_short(reader),
        "email": reader.email,
        "phone": reader.phone,
        "registered_at": reader.registered_at.isoformat(),
        "on_hand": state.active_loans,
        "overdue": state.overdue_loans,
        "fines_total": str(fines_paid + fines_accrued),
        "can_borrow": state.overdue_loans == 0 and state.active_loans < rules.MAX_ACTIVE_LOANS,
        "loans": history,
    }


# ---------- книги ----------

def _copy_on_hand(copy: Copy) -> Optional[Loan]:
    for loan in copy.loans:
        if loan.returned_at is None:
            return loan
    return None


def list_books(session: Session, page: int, size: int, q: Optional[str] = None) -> dict:
    stmt = select(Book)
    if q:
        pattern = f"%{q}%"
        stmt = stmt.where(or_(Book.title.ilike(pattern), Book.author.ilike(pattern)))
    total = session.scalar(select(func.count()).select_from(stmt.subquery()))
    books = session.scalars(stmt.order_by(Book.title, Book.id)
                            .offset((page - 1) * size).limit(size)).all()
    items = []
    for book in books:
        free = sum(1 for copy in book.copies if _copy_on_hand(copy) is None)
        items.append(dict(book_short(book), year=book.year,
                          copies_total=len(book.copies), copies_free=free))
    return {"items": items, "total": total, "page": page, "size": size}


def get_book(session: Session, today: date, book_id: int) -> dict:
    book = session.get(Book, book_id)
    if book is None:
        raise NotFound("book_not_found", "Книга не найдена")
    copies = []
    times_loaned = 0
    for copy in sorted(book.copies, key=lambda c: c.id):
        times_loaned += len(copy.loans)
        current = _copy_on_hand(copy)
        copies.append({
            "id": copy.id,
            "inventory_number": copy.inventory_number,
            "shelf": copy.shelf,
            "status": "free" if current is None else
                      rules.loan_status(current.due_at, None, today),
            "loan_id": current.id if current else None,
            "due_at": current.due_at.isoformat() if current else None,
            "reader": reader_short(current.reader) if current else None,
        })
    return {**book_short(book), "year": book.year, "isbn": book.isbn,
            "times_loaned": times_loaned, "copies": copies}


# ---------- сводка ----------

def summary(session: Session, today: date, top: int = 10) -> dict:
    on_hand = session.scalars(select(Loan).where(Loan.returned_at.is_(None))).all()
    overdue = [loan for loan in on_hand if loan.due_at < today]
    total_copies = session.scalar(select(func.count()).select_from(Copy))
    popular = session.execute(
        select(Book.id, Book.title, Book.author, func.count(Loan.id).label("loans"))
        .join(Copy, Copy.book_id == Book.id)
        .join(Loan, Loan.copy_id == Copy.id)
        .group_by(Book.id)
        .order_by(func.count(Loan.id).desc(), Book.id)
        .limit(top)
    ).all()
    return {
        "date": today.isoformat(),
        "copies_total": total_copies,
        "on_hand": len(on_hand),
        "overdue": len(overdue),
        "overdue_share": round(len(overdue) / len(on_hand), 4) if on_hand else 0.0,
        "fines_accrued": str(sum(rules.fine_for(l.due_at, None, today) for l in overdue)),
        "top_books": [
            {"id": row.id, "title": row.title, "author": row.author, "loans": row.loans}
            for row in popular
        ],
    }
