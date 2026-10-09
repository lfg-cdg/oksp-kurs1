"""Настройки сервиса из переменных окружения (и файла .env, если он есть)."""
import os
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load_dotenv(path: Path = ROOT / ".env") -> None:
    """Минимальный разбор .env: строки ИМЯ=значение, переменные окружения важнее."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.split(" #", 1)[0].strip())


load_dotenv()


class Config:
    DATABASE_URL = os.environ.get(
        "DATABASE_URL",
        "postgresql+psycopg://app:changeme@localhost:5432/mikhail_voronchikhin",
    )
    DB_SCHEMA = os.environ.get("DB_SCHEMA", "mikhail_voronchikhin")
    SECRET_KEY = os.environ.get("SECRET_KEY", "changeme")
    # Фиксированная «сегодняшняя» дата: нужна тестам и воспроизводимым замерам.
    # Пусто — берётся текущая дата.
    APP_TODAY = os.environ.get("APP_TODAY", "")


def today_from(value: str) -> date:
    return date.fromisoformat(value) if value else date.today()
