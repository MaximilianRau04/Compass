from datetime import date, datetime, time

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.calendar import CalendarEvent
from app.services.clock import local_tz


def events_between(session: Session, start: date, end: date) -> list[CalendarEvent]:
    """Events overlapping the local days [start, end), sorted by start."""
    tz = local_tz()
    start_at = datetime.combine(start, time.min, tzinfo=tz)
    end_at = datetime.combine(end, time.min, tzinfo=tz)
    stmt = (
        select(CalendarEvent)
        .where(
            CalendarEvent.starts_at < end_at,
            or_(CalendarEvent.starts_at >= start_at, CalendarEvent.ends_at > start_at),
        )
        .order_by(CalendarEvent.all_day.desc(), CalendarEvent.starts_at, CalendarEvent.title)
    )
    return list(session.scalars(stmt))
