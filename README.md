# Выдача книг в библиотеке — mikhail_voronchikhin

Сервис для библиотекаря: выдаёт экземпляры книг читателям, принимает возврат, считает
просрочку и штраф, показывает сводку по фонду. Учебный сервис курсовой работы по дисциплине
«Оптимизация клиент-серверных приложений», вариант 1. Автор — Ворончихин Михаил, БИСТ-24-ПО-3.

Правила выдачи:

- экземпляр выдаётся, только если он свободен (нет невозвращённой выдачи);
- читателю, у которого есть просроченная выдача, новая выдача запрещена;
- на руках у читателя одновременно не больше 5 экземпляров;
- срок выдачи — 14 дней по умолчанию (от 1 до 60);
- просрочка — дни между сроком возврата и фактической датой возврата;
- штраф — 10 ₽ за каждый день просрочки, фиксируется при возврате.

## Требования

- Python 3.13 (проверено на 3.13.16);
- PostgreSQL 16 (проверено на 16.15);
- зависимости Python — в `requirements.txt`: Flask 3.1.3, SQLAlchemy 2.0.43,
  psycopg 3.2.10, gunicorn 23.0.0, pytest 8.4.2, requests 2.34.2, matplotlib 3.11.2.

## Установка и запуск

```bash
git clone https://github.com/lfg-cdg/oksp-kurs1.git
cd oksp-kurs1
cp .env.example .env
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
sudo -u postgres psql -c "CREATE ROLE app LOGIN PASSWORD 'changeme';"
sudo -u postgres psql -c "CREATE DATABASE mikhail_voronchikhin OWNER app;"
sudo -u postgres psql -c "CREATE DATABASE mikhail_voronchikhin_test OWNER app;"
python manage.py init-db
python manage.py seed --size small
gunicorn -w 1 -b 127.0.0.1:8080 "app:create_app()"
```

`init-db` создаёт схему `mikhail_voronchikhin` по файлу `schema.sql` (старая схема удаляется).
Рабочее наполнение — `python manage.py seed --size work` (около 6 секунд).
Повторный запуск наполнения даёт ту же базу: генератор с зерном 42, даты строятся от
опорной даты 2026-10-01. Проверка — `python manage.py checksum` выводит одинаковую
контрольную сумму после каждого наполнения одного объёма.

## Переменные окружения

| Переменная | Назначение | Пример |
|---|---|---|
| `DATABASE_URL` | подключение к базе данных | `postgresql+psycopg://app:changeme@localhost:5432/mikhail_voronchikhin` |
| `DB_SCHEMA` | схема внутри базы (префикс работы) | `mikhail_voronchikhin` |
| `SECRET_KEY` | ключ подписи куки сессии | `changeme` |
| `APP_TODAY` | «сегодняшняя» дата сервиса; пусто — текущая дата | `2026-10-01` |
| `APP_PORT` | порт сервиса для `bench/server.sh` | `8080` |
| `TEST_DATABASE_URL` | база для тестов | `postgresql+psycopg://app:changeme@localhost:5432/mikhail_voronchikhin_test` |

`APP_TODAY` совпадает с опорной датой наполнения: так статусы выдач («в срок»,
«просрочена») и замеры воспроизводимы в любой день.

## Проверка работоспособности

Интерфейс открывается по адресу http://127.0.0.1:8080, учётная запись — **demo / demo**
(создаётся при наполнении). После входа открывается список выдач с фильтром по статусу и
поиском, оттуда — карточка выдачи (книга, экземпляр, читатель, что ещё у него на руках) и
сводка (меню «Сводка»).

| Экран | Адрес |
|---|---|
| Список выдач с фильтром и постраничным выводом | `/loans?status=overdue&q=&page=1` |
| Карточка выдачи со связанными сущностями | `/loans/<id>` |
| Сводка по всем данным | `/summary` |
| Выдать экземпляр | `/loans/new` |
| Читатели, карточка читателя | `/readers`, `/readers/<id>` |
| Книги, карточка книги с экземплярами | `/books`, `/books/<id>` |

## Тесты

```bash
python -m pytest
```

Тесты используют отдельную базу `TEST_DATABASE_URL`; схема и данные готовятся самими тестами.
Набор: 6 тестов бизнес-правил (`tests/test_rules.py`), 33 теста операций интерфейса
(`tests/test_api.py`), 2 теста экранов (`tests/test_pages.py`).

## Программный интерфейс

Авторизация — сессия в куке: `POST /api/login`, затем кука `session` передаётся с каждым
запросом. Без входа все операции, кроме входа и выхода, отвечают `401`.
Тело запросов и ответов — JSON. Ошибка всегда имеет вид `{"error": "<код>", "message": "<текст>"}`.

| Метод и путь | Параметры | Ответ | Ошибки |
|---|---|---|---|
| `POST /api/login` | тело: `login`, `password` | 200 `{"id", "login", "full_name"}` и кука сессии | 401 неверный логин/пароль, 422 нет полей |
| `POST /api/logout` | — | 204 | — |
| `GET /api/loans` | `page` ≥ 1 (1), `size` 1–100 (20), `status` = `active` \| `overdue` \| `returned` \| `on_hand`, `q` — подстрока ФИО читателя или названия книги, `reader_id` | 200 `{"items": [выдача], "total", "page", "size"}`, сортировка — новые выдачи первыми | 401, 422 |
| `GET /api/loans/{id}` | — | 200 выдача + `reader.email/phone`, `book.year/isbn`, `copy.shelf`, `reader_on_hand: [выдача]` | 401, 404 |
| `POST /api/loans` | тело: `reader_id`, `copy_id`, `days` (14, от 1 до 60) | 201 созданная выдача | 401, 404 экземпляр/читатель не найден, 409 `copy_not_free` \| `reader_has_overdue` \| `reader_limit`, 422 |
| `POST /api/loans/{id}/return` | тело: `returned_at` (ГГГГ-ММ-ДД, по умолчанию сегодня) | 200 выдача с `returned_at`, `overdue_days`, `fine` | 401, 404, 409 `already_returned`, 422 неверная дата |
| `GET /api/readers` | `page`, `size`, `q` — подстрока ФИО или номера билета | 200 `{"items": [{"id", "full_name", "card_number", "email"}], "total", "page", "size"}` | 401, 422 |
| `GET /api/readers/{id}` | — | 200 читатель + `on_hand`, `overdue`, `fines_total`, `can_borrow`, `loans: [выдача]` | 401, 404 |
| `GET /api/books` | `page`, `size`, `q` — подстрока названия или автора | 200 `{"items": [{"id", "title", "author", "year", "copies_total", "copies_free"}], "total", "page", "size"}` | 401, 422 |
| `GET /api/books/{id}` | — | 200 книга + `times_loaned`, `copies: [{"id", "inventory_number", "shelf", "status", "loan_id", "due_at", "reader"}]` | 401, 404 |
| `GET /api/summary` | — | 200 `{"date", "copies_total", "on_hand", "overdue", "overdue_share", "fines_accrued", "top_books": [{"id", "title", "author", "loans"}]}` | 401 |

Объект «выдача»:

```json
{"id": 254, "issued_at": "2026-09-16", "due_at": "2026-09-30", "returned_at": null,
 "status": "overdue", "overdue_days": 1, "fine": "10.00",
 "reader": {"id": 46, "full_name": "…", "card_number": "Б-100046"},
 "copy": {"id": 195, "inventory_number": "ИНВ-000195"},
 "book": {"id": 98, "title": "…", "author": "…"}}
```

`status`: `active` — на руках в срок, `overdue` — на руках и просрочена, `returned` — возвращена.
`fine` у невозвращённой выдачи — начисленный на сегодня штраф, у возвращённой — зафиксированный.

Каждый ответ содержит заголовки `X-DB-Queries` (число запросов к базе), `X-DB-Time-ms`
(их суммарное время) и `X-App-Time-ms` (время обработки в сервисе) — по ним время операции
раскладывается между базой данных и кодом.

## Замеры

```bash
python manage.py seed --size small && ./bench/server.sh start
python bench/bench.py --label small && ./bench/server.sh stop
python manage.py seed --size work && ./bench/server.sh start
python bench/bench.py --label work && ./bench/server.sh stop
python bench/analyze.py
```

`bench.py` входит под demo, по каждой операции делает 5 запросов прогрева и 30 запросов
серии, сохраняет сырые значения в `bench/results/<label>.json`. `analyze.py` строит
`bench/results/tables.md`, `response_time.png` и `db_split.png`.
Операции записи добавляют в базу 35 выдач (и сразу принимают по ним возврат).

## Структура

```
app/            сервис: модели, правила, операции, API, страницы
  rules.py      бизнес-правила без базы данных
  services.py   операции (общие для API и страниц)
manage.py       создание схемы, наполнение, контрольная сумма
schema.sql      схема базы данных
tests/          модульные тесты
bench/          скрипты и результаты замеров
```
