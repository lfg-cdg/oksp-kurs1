-- Схема сервиса «Выдача книг в библиотеке» (вариант 1).
-- Префикс работы: mikhail_voronchikhin.
-- Индексов сверх первичных ключей нет (ограничение первого задания).
-- Единственное исключение — UNIQUE на логин библиотекаря: он нужен для
-- корректности входа, а таблица из одной-двух строк на замеры не влияет.

DROP SCHEMA IF EXISTS mikhail_voronchikhin CASCADE;
CREATE SCHEMA mikhail_voronchikhin;
SET search_path TO mikhail_voronchikhin;

-- Учётные записи библиотекарей (вход в сервис).
CREATE TABLE librarian (
    id            serial PRIMARY KEY,
    login         text NOT NULL UNIQUE,
    password_hash text NOT NULL,
    full_name     text NOT NULL
);

-- Читатель.
CREATE TABLE reader (
    id            serial PRIMARY KEY,
    full_name     text NOT NULL,
    card_number   text NOT NULL,
    email         text,
    phone         text,
    registered_at date NOT NULL
);

-- Книга (издание).
CREATE TABLE book (
    id     serial PRIMARY KEY,
    title  text NOT NULL,
    author text NOT NULL,
    year   integer,
    isbn   text
);

-- Экземпляр книги.
CREATE TABLE copy (
    id               serial PRIMARY KEY,
    book_id          integer NOT NULL REFERENCES book (id),
    inventory_number text NOT NULL,
    shelf            text
);

-- Выдача экземпляра читателю — основная операционная таблица.
CREATE TABLE loan (
    id          serial PRIMARY KEY,
    copy_id     integer NOT NULL REFERENCES copy (id),
    reader_id   integer NOT NULL REFERENCES reader (id),
    issued_at   date NOT NULL,
    due_at      date NOT NULL,
    returned_at date,
    fine        numeric(10, 2),
    CHECK (due_at >= issued_at),
    CHECK (returned_at IS NULL OR returned_at >= issued_at)
);
