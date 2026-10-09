"""Бизнес-правила варианта 1 без обращения к базе данных.

Правила:
* экземпляр выдаётся, только если он свободен (нет невозвращённой выдачи);
* читателю с просроченной выдачей новая выдача запрещена;
* на руках у читателя одновременно не больше MAX_ACTIVE_LOANS экземпляров
  (уточнение правила, допускаемое сноской к таблице 2 методички);
* просрочка — число дней между сроком возврата и фактической датой возврата
  (или сегодняшней датой, если книга ещё на руках);
* штраф — FINE_PER_DAY рублей за каждый день просрочки.
"""
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Optional

LOAN_DAYS = 14
MAX_LOAN_DAYS = 60
MAX_ACTIVE_LOANS = 5
FINE_PER_DAY = Decimal("10.00")


class IssueRejected(Exception):
    """Выдача отклонена по правилу. code — машиночитаемая причина."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def overdue_days(due_at: date, returned_at: Optional[date], today: date) -> int:
    """Дни просрочки: от срока возврата до даты возврата (или до сегодня)."""
    end = returned_at or today
    return max(0, (end - due_at).days)


def fine_for(due_at: date, returned_at: Optional[date], today: date) -> Decimal:
    """Штраф за просрочку в рублях."""
    return FINE_PER_DAY * overdue_days(due_at, returned_at, today)


def loan_status(due_at: date, returned_at: Optional[date], today: date) -> str:
    """returned — возвращена, overdue — на руках и просрочена, active — на руках в срок."""
    if returned_at is not None:
        return "returned"
    return "overdue" if due_at < today else "active"


@dataclass
class ReaderState:
    active_loans: int
    overdue_loans: int


def check_issue(copy_is_free: bool, reader: ReaderState) -> None:
    """Проверяет, можно ли выдать экземпляр. Бросает IssueRejected, если нельзя."""
    if not copy_is_free:
        raise IssueRejected("copy_not_free", "Экземпляр уже выдан и не возвращён")
    if reader.overdue_loans > 0:
        raise IssueRejected("reader_has_overdue", "У читателя есть просроченные выдачи")
    if reader.active_loans >= MAX_ACTIVE_LOANS:
        raise IssueRejected(
            "reader_limit", f"У читателя на руках уже {MAX_ACTIVE_LOANS} экземпляров"
        )
