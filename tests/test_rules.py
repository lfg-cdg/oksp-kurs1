"""Тесты бизнес-правил варианта 1: без базы данных и без работающего сервиса."""
from datetime import date
from decimal import Decimal

import pytest

from app import rules

DUE = date(2026, 10, 1)


def test_returned_on_time_has_no_overdue_and_no_fine():
    assert rules.overdue_days(DUE, date(2026, 9, 28), today=date(2026, 10, 5)) == 0
    assert rules.fine_for(DUE, date(2026, 10, 1), today=date(2026, 10, 5)) == Decimal("0")


def test_fine_is_ten_rubles_per_overdue_day():
    returned = date(2026, 10, 8)  # срок возврата DUE = 2026-10-01
    assert rules.overdue_days(DUE, returned, today=returned) == 7
    assert rules.fine_for(DUE, returned, today=returned) == Decimal("70.00")


def test_overdue_of_book_on_hand_is_counted_to_today():
    assert rules.overdue_days(DUE, None, today=date(2026, 10, 4)) == 3
    assert rules.loan_status(DUE, None, today=date(2026, 10, 4)) == "overdue"
    assert rules.loan_status(DUE, None, today=date(2026, 10, 1)) == "active"
    assert rules.loan_status(DUE, date(2026, 10, 2), today=date(2026, 10, 4)) == "returned"


def test_busy_copy_cannot_be_issued():
    with pytest.raises(rules.IssueRejected) as exc:
        rules.check_issue(copy_is_free=False, reader=rules.ReaderState(0, 0))
    assert exc.value.code == "copy_not_free"


def test_reader_with_overdue_loan_cannot_borrow():
    with pytest.raises(rules.IssueRejected) as exc:
        rules.check_issue(copy_is_free=True, reader=rules.ReaderState(1, 1))
    assert exc.value.code == "reader_has_overdue"


def test_reader_limit_of_active_loans():
    with pytest.raises(rules.IssueRejected) as exc:
        rules.check_issue(copy_is_free=True,
                          reader=rules.ReaderState(rules.MAX_ACTIVE_LOANS, 0))
    assert exc.value.code == "reader_limit"
    rules.check_issue(copy_is_free=True,
                      reader=rules.ReaderState(rules.MAX_ACTIVE_LOANS - 1, 0))
