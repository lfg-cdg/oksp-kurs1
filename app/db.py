"""Подключение к PostgreSQL и учёт времени запросов к базе данных.

Для каждого HTTP-запроса считаются число SQL-запросов и их суммарное время
(отметки времени вокруг выполнения курсора). Значения отдаются в заголовках
ответа X-DB-Queries и X-DB-Time-ms — по ним время операции раскладывается
между базой данных и кодом приложения.
"""
import time

from flask import g, has_request_context
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import scoped_session, sessionmaker


def make_engine(url: str, schema: str) -> Engine:
    engine = create_engine(
        url,
        connect_args={"options": f"-csearch_path={schema}"},
        pool_size=5,
        pool_pre_ping=True,
    )

    @event.listens_for(engine, "before_cursor_execute")
    def _before(conn, cursor, statement, parameters, context, executemany):
        conn.info.setdefault("query_start", []).append(time.perf_counter())

    @event.listens_for(engine, "after_cursor_execute")
    def _after(conn, cursor, statement, parameters, context, executemany):
        started = conn.info["query_start"].pop()
        if has_request_context():
            g.db_queries = g.get("db_queries", 0) + 1
            g.db_time = g.get("db_time", 0.0) + (time.perf_counter() - started)

    @event.listens_for(engine, "handle_error")
    def _error(context):
        stack = context.connection.info.get("query_start") if context.connection else None
        if stack:
            stack.pop()

    return engine


def make_session_factory(engine: Engine) -> scoped_session:
    return scoped_session(sessionmaker(bind=engine, expire_on_commit=False))
