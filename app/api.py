"""Программный интерфейс /api. Контракт описан в README.md."""
from functools import wraps

from flask import Blueprint, g, jsonify, request, session

from . import services as svc

api = Blueprint("api", __name__, url_prefix="/api")


def api_login_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            return jsonify(error="unauthorized", message="Требуется вход"), 401
        return view(*args, **kwargs)
    return wrapper


@api.errorhandler(svc.ServiceError)
def _service_error(exc: svc.ServiceError):
    return jsonify(error=exc.code, message=exc.message), exc.status


def _body() -> dict:
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise svc.Invalid("invalid_body", "Тело запроса должно быть объектом JSON")
    return data


@api.post("/login")
def login():
    data = _body()
    if not data.get("login") or not data.get("password"):
        raise svc.Invalid("invalid_body", "Нужны поля login и password")
    try:
        user = svc.authenticate(g.session, data["login"], data["password"])
    except svc.ServiceError as exc:
        return jsonify(error=exc.code, message=exc.message), 401
    session.clear()
    session["user_id"] = user.id
    session["user_name"] = user.full_name
    return jsonify(id=user.id, login=user.login, full_name=user.full_name)


@api.post("/logout")
def logout():
    session.clear()
    return "", 204


@api.get("/loans")
@api_login_required
def loans_list():
    page, size = svc.parse_paging(request.args)
    reader_id = request.args.get("reader_id")
    return jsonify(svc.list_loans(
        g.session, g.today, page, size,
        status=request.args.get("status") or None,
        q=request.args.get("q") or None,
        reader_id=svc.parse_int(reader_id, "reader_id", minimum=1) if reader_id else None,
    ))


@api.get("/loans/<int:loan_id>")
@api_login_required
def loan_card(loan_id: int):
    return jsonify(svc.get_loan(g.session, g.today, loan_id))


@api.post("/loans")
@api_login_required
def loan_create():
    data = _body()
    loan = svc.create_loan(
        g.session, g.today,
        reader_id=svc.parse_int(data.get("reader_id"), "reader_id", minimum=1),
        copy_id=svc.parse_int(data.get("copy_id"), "copy_id", minimum=1),
        days=svc.parse_int(data.get("days"), "days", default=14),
    )
    return jsonify(loan), 201


@api.post("/loans/<int:loan_id>/return")
@api_login_required
def loan_return(loan_id: int):
    data = request.get_json(silent=True) or {}
    returned_at = svc.parse_date(data.get("returned_at"), "returned_at", g.today)
    return jsonify(svc.return_loan(g.session, g.today, loan_id, returned_at))


@api.get("/readers")
@api_login_required
def readers_list():
    page, size = svc.parse_paging(request.args)
    return jsonify(svc.list_readers(g.session, page, size, q=request.args.get("q") or None))


@api.get("/readers/<int:reader_id>")
@api_login_required
def reader_card(reader_id: int):
    return jsonify(svc.get_reader(g.session, g.today, reader_id))


@api.get("/books")
@api_login_required
def books_list():
    page, size = svc.parse_paging(request.args)
    return jsonify(svc.list_books(g.session, page, size, q=request.args.get("q") or None))


@api.get("/books/<int:book_id>")
@api_login_required
def book_card(book_id: int):
    return jsonify(svc.get_book(g.session, g.today, book_id))


@api.get("/summary")
@api_login_required
def summary():
    return jsonify(svc.summary(g.session, g.today))
