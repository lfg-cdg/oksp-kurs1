"""Тесты операций программного интерфейса: коды ответа, состав полей, ошибки."""
import pytest

PROTECTED = [
    ("get", "/api/loans"), ("get", "/api/loans/1"), ("post", "/api/loans"),
    ("post", "/api/loans/1/return"), ("get", "/api/readers"), ("get", "/api/readers/1"),
    ("get", "/api/books"), ("get", "/api/books/1"), ("get", "/api/summary"),
]


@pytest.mark.parametrize("method,path", PROTECTED)
def test_operations_require_authorization(client, method, path):
    response = getattr(client, method)(path, json={})
    assert response.status_code == 401
    assert response.get_json()["error"] == "unauthorized"


def test_login_with_wrong_password_is_rejected(client):
    response = client.post("/api/login", json={"login": "demo", "password": "nope"})
    assert response.status_code == 401


def test_login_requires_fields(client):
    assert client.post("/api/login", json={"login": "demo"}).status_code == 422


def test_logout_ends_session(auth_client):
    assert auth_client.post("/api/logout").status_code == 204
    assert auth_client.get("/api/loans").status_code == 401


def test_loans_list_returns_page_and_total(auth_client):
    response = auth_client.get("/api/loans?page=1&size=2")
    assert response.status_code == 200
    body = response.get_json()
    assert set(body) == {"items", "total", "page", "size"}
    assert body["total"] == 3 and len(body["items"]) == 2
    item = body["items"][0]
    assert set(item) == {"id", "issued_at", "due_at", "returned_at", "status", "overdue_days",
                         "fine", "reader", "copy", "book"}


def test_loans_list_filters_by_status_and_text(auth_client):
    overdue = auth_client.get("/api/loans?status=overdue").get_json()
    assert overdue["total"] == 1
    assert overdue["items"][0]["reader"]["full_name"] == "Петрова Анна"
    assert overdue["items"][0]["fine"] == "50.00"
    found = auth_client.get("/api/loans?q=Сидоров").get_json()
    assert found["total"] == 1 and found["items"][0]["status"] == "returned"


@pytest.mark.parametrize("query", ["page=0", "size=101", "size=abc", "status=lost"])
def test_loans_list_rejects_bad_params(auth_client, query):
    assert auth_client.get(f"/api/loans?{query}").status_code == 422


def test_loan_card_contains_related_entities(auth_client):
    body = auth_client.get("/api/loans/1").get_json()
    assert body["reader"]["full_name"] == "Иванов Иван"
    assert body["book"]["title"] == "Тихий сад"
    assert body["copy"]["inventory_number"] == "ИНВ-1"
    assert body["reader_on_hand"] == []


def test_loan_card_not_found(auth_client):
    assert auth_client.get("/api/loans/999").status_code == 404


def test_issue_free_copy_returns_201(auth_client):
    response = auth_client.post("/api/loans", json={"reader_id": 3, "copy_id": 4})
    assert response.status_code == 201
    body = response.get_json()
    assert body["status"] == "active"
    assert body["issued_at"] == "2026-10-01" and body["due_at"] == "2026-10-15"


def test_issue_busy_copy_returns_409(auth_client):
    response = auth_client.post("/api/loans", json={"reader_id": 3, "copy_id": 1})
    assert response.status_code == 409
    assert response.get_json()["error"] == "copy_not_free"


def test_issue_to_reader_with_overdue_returns_409(auth_client):
    # У читателя 2 просрочка 5 дней, экземпляр 4 свободен.
    response = auth_client.post("/api/loans",
                                json={"reader_id": 2, "copy_id": 4})
    assert response.status_code == 409
    assert response.get_json()["error"] == "reader_has_overdue"


def test_issue_unknown_copy_or_reader_returns_404(auth_client):
    assert auth_client.post("/api/loans", json={"reader_id": 3, "copy_id": 99}).status_code == 404
    assert auth_client.post("/api/loans", json={"reader_id": 99, "copy_id": 4}).status_code == 404


def test_issue_with_bad_body_returns_422(auth_client):
    assert auth_client.post("/api/loans", json={"reader_id": "x", "copy_id": 4}).status_code == 422
    assert auth_client.post("/api/loans", json={"reader_id": 3, "copy_id": 4,
                                                "days": 0}).status_code == 422


def test_return_overdue_loan_fixes_date_and_fine(auth_client):
    response = auth_client.post("/api/loans/2/return", json={})
    assert response.status_code == 200
    body = response.get_json()
    assert body["returned_at"] == "2026-10-01"
    assert body["overdue_days"] == 5 and body["fine"] == "50.00"
    assert body["status"] == "returned"
    # После возврата экземпляр снова можно выдать.
    assert auth_client.post("/api/loans", json={"reader_id": 3, "copy_id": 2}).status_code == 201


def test_return_twice_returns_409(auth_client):
    assert auth_client.post("/api/loans/3/return", json={}).status_code == 409


def test_return_with_bad_date_returns_422(auth_client):
    assert auth_client.post("/api/loans/1/return",
                            json={"returned_at": "2026-13-01"}).status_code == 422
    assert auth_client.post("/api/loans/1/return",
                            json={"returned_at": "2020-01-01"}).status_code == 422


def test_reader_card_has_debt_and_history(auth_client):
    body = auth_client.get("/api/readers/2").get_json()
    assert body["on_hand"] == 1 and body["overdue"] == 1
    assert body["fines_total"] == "50.00" and body["can_borrow"] is False
    assert len(body["loans"]) == 1
    assert auth_client.get("/api/readers/99").status_code == 404


def test_readers_list_search(auth_client):
    body = auth_client.get("/api/readers?q=Петрова").get_json()
    assert body["total"] == 1 and body["items"][0]["id"] == 2


def test_books_list_counts_free_copies(auth_client):
    body = auth_client.get("/api/books").get_json()
    assert body["total"] == 1
    assert body["items"][0]["copies_total"] == 4 and body["items"][0]["copies_free"] == 2


def test_book_card_shows_copy_statuses(auth_client):
    body = auth_client.get("/api/books/1").get_json()
    assert [c["status"] for c in body["copies"]] == ["active", "overdue", "free", "free"]
    assert body["times_loaned"] == 3
    assert auth_client.get("/api/books/99").status_code == 404


def test_summary_counts_on_hand_overdue_and_top(auth_client):
    body = auth_client.get("/api/summary").get_json()
    assert body["on_hand"] == 2 and body["overdue"] == 1
    assert body["overdue_share"] == 0.5
    assert body["copies_total"] == 4
    assert body["top_books"] == [{"id": 1, "title": "Тихий сад", "author": "Орлов Илья", "loans": 3}]
