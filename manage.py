"""Служебные команды сервиса.

    python manage.py init-db               # создать схему (удаляет старую!)
    python manage.py seed --size small     # малое наполнение
    python manage.py seed --size work      # рабочее наполнение
    python manage.py counts                # число записей по таблицам
    python manage.py checksum              # контрольная сумма данных
"""
import argparse
import random
import sys
import time
from datetime import date, timedelta
from pathlib import Path

import psycopg
from werkzeug.security import generate_password_hash

sys.path.insert(0, str(Path(__file__).resolve().parent))
from app.config import Config  # noqa: E402
from app.rules import FINE_PER_DAY, LOAN_DAYS, MAX_ACTIVE_LOANS  # noqa: E402

ROOT = Path(__file__).resolve().parent
SEED = 42
# Опорная дата наполнения: все даты выдач строятся относительно неё,
# поэтому повторный запуск даёт ту же базу независимо от дня запуска.
SEED_TODAY = date(2026, 10, 1)

SIZES = {
    "small": {"readers": 50, "books": 100, "copies": 200, "loans": 300},
    "work": {"readers": 3000, "books": 10000, "copies": 30000, "loans": 100000},
}

LAST = ["Иванов", "Смирнов", "Кузнецов", "Попов", "Васильев", "Петров", "Соколов", "Михайлов",
        "Новиков", "Фёдоров", "Морозов", "Волков", "Алексеев", "Лебедев", "Семёнов", "Егоров",
        "Павлов", "Козлов", "Степанов", "Николаев", "Орлов", "Андреев", "Макаров", "Никитин",
        "Захаров", "Зайцев", "Соловьёв", "Борисов", "Яковлев", "Григорьев", "Романов", "Воробьёв"]
FIRST_M = ["Александр", "Дмитрий", "Максим", "Сергей", "Андрей", "Алексей", "Артём", "Илья",
           "Кирилл", "Михаил", "Никита", "Матвей", "Роман", "Егор", "Арсений", "Иван"]
FIRST_F = ["Анастасия", "Мария", "Анна", "Виктория", "Екатерина", "Наталья", "Марина", "Полина",
           "Дарья", "Алиса", "Ксения", "Елизавета", "Софья", "Ольга", "Татьяна", "Юлия"]
PATR = ["Александров", "Дмитриев", "Сергеев", "Андреев", "Алексеев", "Иванов", "Михайлов",
        "Николаев", "Петров", "Владимиров", "Викторов", "Павлов"]
ADJ = ["Тихий", "Последний", "Северный", "Забытый", "Красный", "Далёкий", "Ночной", "Старый",
       "Белый", "Тёмный", "Золотой", "Ледяной", "Короткий", "Долгий", "Странный", "Новый",
       "Пустой", "Медленный", "Верный", "Шестой"]
NOUN = ["сад", "город", "берег", "дом", "путь", "ветер", "остров", "мост", "лес", "огонь",
        "голос", "век", "поезд", "маяк", "архив", "перевал", "колодец", "двор", "свет", "час"]
TAIL = ["", "", "", " и другие рассказы", ": роман", ". Книга первая", ". Книга вторая",
        " в трёх частях", ": хроника", ": записки"]


def db_url() -> str:
    return Config.DATABASE_URL.replace("postgresql+psycopg://", "postgresql://")


def connect():
    return psycopg.connect(db_url(), options=f"-csearch_path={Config.DB_SCHEMA}")


def init_db() -> None:
    sql = (ROOT / "schema.sql").read_text(encoding="utf-8")
    with psycopg.connect(db_url()) as conn:
        conn.execute(sql)
    print(f"Схема {Config.DB_SCHEMA} создана")


def person(rng: random.Random) -> str:
    if rng.random() < 0.5:
        return f"{rng.choice(LAST)} {rng.choice(FIRST_M)} {rng.choice(PATR)}ич"
    return f"{rng.choice(LAST)}а {rng.choice(FIRST_F)} {rng.choice(PATR)}на"


def generate(size: str) -> dict:
    """Строит все строки в памяти. Генератор с фиксированным зерном — результат одинаков."""
    n = SIZES[size]
    rng = random.Random(SEED)

    readers = []
    for i in range(1, n["readers"] + 1):
        readers.append((i, person(rng), f"Б-{100000 + i}", f"reader{i}@example.org",
                        f"+7 9{rng.randint(10, 99)} {rng.randint(100, 999)}-{rng.randint(10, 99)}-{rng.randint(10, 99)}",
                        SEED_TODAY - timedelta(days=rng.randint(30, 3000))))

    authors = [person(rng).rsplit(" ", 1)[0] for _ in range(max(20, n["books"] // 8))]
    books = []
    for i in range(1, n["books"] + 1):
        title = f"{rng.choice(ADJ)} {rng.choice(NOUN)}{rng.choice(TAIL)}"
        books.append((i, title, rng.choice(authors), rng.randint(1950, 2025),
                      f"978-5-{rng.randint(1000, 9999)}-{rng.randint(1000, 9999)}-{rng.randint(0, 9)}"))

    # Экземпляры: у каждой книги хотя бы один, остальные распределяются случайно.
    copy_book = list(range(1, n["books"] + 1))
    copy_book += [rng.randint(1, n["books"]) for _ in range(n["copies"] - n["books"])]
    copy_book.sort()
    copies = [(i, b, f"ИНВ-{i:06d}", f"{rng.choice('АБВГДЕЖЗ')}-{rng.randint(1, 40)}")
              for i, b in enumerate(copy_book, start=1)]

    # Популярность книги — степенное распределение: немногие книги берут часто.
    popularity = {b: 1.0 / (rank ** 0.8)
                  for rank, b in enumerate(rng.sample(range(1, n["books"] + 1), n["books"]), start=1)}
    weights = [popularity[c[1]] for c in copies]
    per_copy = [0] * len(copies)
    for idx in rng.choices(range(len(copies)), weights=weights, k=n["loans"]):
        per_copy[idx] += 1

    active_by_reader = [0] * (n["readers"] + 1)
    loans = []
    for idx, count in enumerate(per_copy):
        copy_id = copies[idx][0]
        cursor = SEED_TODAY
        for k in range(count):
            reader_id = rng.randint(1, n["readers"])
            on_hand = (k == 0 and rng.random() < 0.3)
            if on_hand and active_by_reader[reader_id] >= MAX_ACTIVE_LOANS:
                on_hand = False
            if on_hand:
                # Большинство на руках в срок, примерно каждая четвёртая — просрочена.
                held_now = rng.randint(1, 16) if rng.random() < 0.85 else rng.randint(17, 60)
                issued = cursor - timedelta(days=held_now)
                due = issued + timedelta(days=LOAN_DAYS)
                loans.append([copy_id, reader_id, issued, due, None, None])
                active_by_reader[reader_id] += 1
                cursor = issued - timedelta(days=rng.randint(1, 30))
                continue
            # Возвращённая выдача: заканчивается до начала следующей по времени.
            held = rng.choice([rng.randint(3, LOAN_DAYS)] * 4 + [rng.randint(LOAN_DAYS + 1, 40)])
            returned = cursor - timedelta(days=rng.randint(0, 30))
            issued = returned - timedelta(days=held)
            due = issued + timedelta(days=LOAN_DAYS)
            fine = FINE_PER_DAY * max(0, (returned - due).days)
            loans.append([copy_id, reader_id, issued, due, returned, fine])
            cursor = issued - timedelta(days=rng.randint(1, 20))

    # Идентификаторы выдач — в хронологическом порядке, как при реальной работе.
    loans.sort(key=lambda r: (r[2], r[0]))
    loans = [(i, *row) for i, row in enumerate(loans, start=1)]
    return {"reader": readers, "book": books, "copy": copies, "loan": loans}


COLUMNS = {
    "reader": "id, full_name, card_number, email, phone, registered_at",
    "book": "id, title, author, year, isbn",
    "copy": "id, book_id, inventory_number, shelf",
    "loan": "id, copy_id, reader_id, issued_at, due_at, returned_at, fine",
}


def seed(size: str) -> None:
    started = time.perf_counter()
    data = generate(size)
    with connect() as conn:
        conn.execute("TRUNCATE loan, copy, book, reader, librarian RESTART IDENTITY")
        for table in ("reader", "book", "copy", "loan"):
            with conn.cursor().copy(f"COPY {table} ({COLUMNS[table]}) FROM STDIN") as cp:
                for row in data[table]:
                    cp.write_row(row)
            conn.execute(f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), "
                         f"(SELECT max(id) FROM {table}))")
        conn.execute(
            "INSERT INTO librarian (login, password_hash, full_name) VALUES (%s, %s, %s)",
            ("demo", generate_password_hash("demo"), "Библиотекарь Демо"),
        )
    with psycopg.connect(db_url(), autocommit=True,
                         options=f"-csearch_path={Config.DB_SCHEMA}") as conn:
        conn.execute("VACUUM ANALYZE")
    print(f"Наполнение «{size}» загружено за {time.perf_counter() - started:.1f} с")
    counts()


def counts() -> None:
    with connect() as conn:
        for table in ("reader", "book", "copy", "loan", "librarian"):
            total = conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
            print(f"{table:<10} {total:>8}")
        on_hand, overdue = conn.execute(
            "SELECT count(*) FILTER (WHERE returned_at IS NULL), "
            "count(*) FILTER (WHERE returned_at IS NULL AND due_at < %s) FROM loan",
            (SEED_TODAY,)).fetchone()
        print(f"на руках   {on_hand:>8}\nпросрочено {overdue:>8}  (на {SEED_TODAY})")


def checksum() -> None:
    """MD5 по содержимому таблиц: совпадает у двух наполнений одного объёма."""
    import hashlib
    digest = hashlib.md5()
    with connect() as conn:
        for table in ("reader", "book", "copy", "loan"):
            for row in conn.execute(f"SELECT {COLUMNS[table]} FROM {table} ORDER BY id"):
                digest.update(repr(row).encode())
    print(f"checksum {digest.hexdigest()}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init-db")
    p_seed = sub.add_parser("seed")
    p_seed.add_argument("--size", choices=SIZES, default="small")
    sub.add_parser("counts")
    sub.add_parser("checksum")
    args = parser.parse_args()
    if args.cmd == "init-db":
        init_db()
    elif args.cmd == "seed":
        seed(args.size)
    elif args.cmd == "checksum":
        checksum()
    else:
        counts()


if __name__ == "__main__":
    main()
