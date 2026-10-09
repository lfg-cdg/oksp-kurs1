"""Обязательные экраны открываются и показывают данные."""


def login_page(client):
    return client.post("/login", data={"login": "demo", "password": "demo"})


def test_pages_redirect_to_login(client):
    response = client.get("/loans")
    assert response.status_code == 302 and "/login" in response.headers["Location"]


def test_required_screens_render(client):
    assert login_page(client).status_code == 302
    # Инвентарный номер экземпляра обязан быть виден в списке и карточке выдачи.
    for path, marker in [("/loans?status=overdue", "Петрова Анна"), ("/loans", "ИНВ-2"),
                         ("/loans/1", "Тихий сад"), ("/loans/1", "ИНВ-1"),
                         ("/summary", "Чаще всего берут"), ("/readers/2", "Просрочено"),
                         ("/books/1", "ИНВ-4"), ("/loans/new", "Выдать экземпляр")]:
        response = client.get(path)
        assert response.status_code == 200, path
        assert marker in response.get_data(as_text=True), path
