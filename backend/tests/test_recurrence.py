from datetime import date

import pytest

from app.services.recurrence import next_occurrence, validate_rrule


def test_weekly_on_time():
    assert next_occurrence("FREQ=WEEKLY;BYDAY=MO", date(2026, 10, 19), date(2026, 10, 19)) == date(
        2026, 10, 26
    )


def test_completed_late_skips_to_today_or_later():
    # Daily task from Monday, completed on Thursday: next instance is Thursday, not Tuesday.
    assert next_occurrence("FREQ=DAILY", date(2026, 10, 12), date(2026, 10, 15)) == date(
        2026, 10, 15
    )


def test_monthly_end_of_month():
    assert next_occurrence("FREQ=MONTHLY", date(2026, 1, 31), date(2026, 1, 31)) == date(
        2026, 3, 31
    )


def test_validate_rejects_garbage():
    with pytest.raises(ValueError):
        validate_rrule("FREQ=SOMETIMES")
    assert validate_rrule("RRULE:FREQ=DAILY") == "FREQ=DAILY"
