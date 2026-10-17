from datetime import date, datetime, timedelta

from dateutil.rrule import rrulestr


def validate_rrule(rule: str) -> str:
    """Raise ValueError if rule is not a valid RRULE body (without the "RRULE:" prefix)."""
    rule = rule.strip().removeprefix("RRULE:")
    rrulestr(f"RRULE:{rule}", dtstart=datetime(2000, 1, 1))
    return rule


def next_occurrence(rule: str, anchor: date, today: date) -> date | None:
    """Next date of the series after anchor, but never in the past.

    anchor is the date of the instance that was just completed. If the task was finished late,
    the next instance is the first occurrence from today on, so it is not overdue right away.
    """
    series = rrulestr(f"RRULE:{rule}", dtstart=datetime.combine(anchor, datetime.min.time()))
    nxt = series.after(datetime.combine(anchor, datetime.min.time()))
    if nxt is not None and nxt.date() < today:
        nxt = series.after(datetime.combine(today - timedelta(days=1), datetime.min.time()))
    return nxt.date() if nxt else None
