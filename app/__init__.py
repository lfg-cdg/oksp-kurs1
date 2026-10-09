"""Сервис «Выдача книг в библиотеке». Фабрика приложения Flask."""
import time

from flask import Flask, g, request

from .config import Config, today_from
from .db import make_engine, make_session_factory


def create_app(overrides: dict | None = None) -> Flask:
    app = Flask(__name__)
    app.config.from_object(Config)
    if overrides:
        app.config.update(overrides)
    app.json.ensure_ascii = False
    app.json.sort_keys = False

    engine = make_engine(app.config["DATABASE_URL"], app.config["DB_SCHEMA"])
    Session = make_session_factory(engine)
    app.extensions["engine"] = engine
    app.extensions["session"] = Session

    @app.before_request
    def _start_timer():
        g.started = time.perf_counter()
        g.db_queries = 0
        g.db_time = 0.0
        g.session = Session()
        g.today = today_from(app.config["APP_TODAY"])

    @app.after_request
    def _timing_headers(response):
        if "started" in g:
            total_ms = (time.perf_counter() - g.started) * 1000
            db_ms = g.db_time * 1000
            response.headers["X-DB-Queries"] = str(g.db_queries)
            response.headers["X-DB-Time-ms"] = f"{db_ms:.3f}"
            response.headers["X-App-Time-ms"] = f"{total_ms:.3f}"
            response.headers["Server-Timing"] = f"db;dur={db_ms:.3f}, total;dur={total_ms:.3f}"
        return response

    @app.teardown_request
    def _close_session(exc):
        Session.remove()

    from .api import api
    from .web import web
    app.register_blueprint(api)
    app.register_blueprint(web)
    return app
