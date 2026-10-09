"""Общие фикстуры. Тесты операций работают с отдельной базой TEST_DATABASE_URL,
схема пересоздаётся перед каждым тестом, данные готовятся здесь же — без ручной подготовки."""
import os
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import psycopg
import pytest
from werkzeug.security import generate_password_hash

from app import create_app
from app.models import Book, Copy, Librarian, Loan, Reader

ROOT = Path(__file__).resolve().parent.parent
TEST_DB = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+psycopg://app:changeme@localhost:5432/mikhail_voronchikhin_test",
)
TODAY = date(2026, 10, 1)


@pytest.fixture
def app():
    with psycopg.connect(TEST_DB.replace("postgresql+psycopg://", "postgresql://")) as conn:
        conn.execute((ROOT / "schema.sql").read_text(encoding="utf-8"))
    app = create_app({"DATABASE_URL": TEST_DB, "APP_TODAY": TODAY.isoformat(),
                      "SECRET_KEY": "test", "TESTING": True})
    session = app.extensions["session"]()
    session.add(Librarian(login="demo", password_hash=generate_password_hash("demo"),
                          full_name="Библиотекарь Демо"))
    readers = [Reader(full_name=name, card_number=f"Б-{i}", email=f"r{i}@example.org",
                      registered_at=date(2024, 1, 1))
               for i, name in enumerate(["Иванов Иван", "Петрова Анна", "Сидоров Пётр"], start=1)]
    book = Book(title="Тихий сад", author="Орлов Илья", year=2001, isbn="978-5-0000-0000-1")
    copies = [Copy(book=book, inventory_number=f"ИНВ-{i}", shelf="А-1") for i in range(1, 5)]
    session.add_all(readers + [book] + copies)
    session.flush()
    session.add_all([
        # Иванов: одна выдача в срок (экземпляр 1 занят).
        Loan(copy=copies[0], reader=readers[0], issued_at=TODAY - timedelta(days=3),
             due_at=TODAY + timedelta(days=11)),
        # Петрова: просрочка 5 дней (экземпляр 2 занят).
        Loan(copy=copies[1], reader=readers[1], issued_at=TODAY - timedelta(days=19),
             due_at=TODAY - timedelta(days=5)),
        # История: возвращённая выдача экземпляра 3.
        Loan(copy=copies[2], reader=readers[2], issued_at=date(2026, 8, 1),
             due_at=date(2026, 8, 15), returned_at=date(2026, 8, 10), fine=Decimal("0")),
    ])
    session.commit()
    session.close()
    app.extensions["session"].remove()
    yield app
    app.extensions["engine"].dispose()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def auth_client(app):
    client = app.test_client()
    response = client.post("/api/login", json={"login": "demo", "password": "demo"})
    assert response.status_code == 200
    return client
