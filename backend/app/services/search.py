"""One search over tasks, notes, calendar events and mails, for the search field of the web app
and for assistants. Each kind is matched its own way: notes by their full text index, the
others by the words appearing in their texts."""

from dataclasses import dataclass, field
from datetime import datetime, time

from sqlalchemy import ColumnElement, and_, case, func, or_, select
from sqlalchemy.orm import Session

from app.models.calendar import CalendarEvent
from app.models.mail import Email
from app.models.tasks import Task
from app.services import notes as note_service
from app.services.clock import local_today, local_tz
from app.services.tasks import ACTIVE, contains

MIN_QUERY = 2


@dataclass
class Results:
    tasks: list[Task] = field(default_factory=list)
    notes: list[note_service.Found] = field(default_factory=list)
    events: list[CalendarEvent] = field(default_factory=list)
    mails: list[Email] = field(default_factory=list)


def _all_words(query: str, *columns) -> ColumnElement[bool]:
    """Every word of the query appears in one of the columns, in any order."""
    return and_(
        *(
            or_(*(column.ilike(contains(word), escape="\\") for column in columns))
            for word in query.split()
        )
    )


def search(session: Session, query: str, limit: int = 8) -> Results:
    query = " ".join(query.split())
    if len(query) < MIN_QUERY:
        return Results()

    # Open tasks first, then what was touched last. Done and discarded ones are found too:
    # "did I already do that?" is a common reason to search.
    tasks = session.scalars(
        select(Task)
        .where(
            _all_words(
                query,
                Task.title,
                func.coalesce(Task.notes, ""),
                func.array_to_string(Task.tags, " "),
            )
        )
        .order_by(case((Task.status.in_(ACTIVE), 0), else_=1), Task.updated_at.desc())
        .limit(limit)
    ).unique()

    # What comes next first (nearest on top), then the past, newest first.
    today_start = datetime.combine(local_today(), time.min, tzinfo=local_tz())
    upcoming = CalendarEvent.starts_at >= today_start
    seconds_away = func.abs(func.extract("epoch", CalendarEvent.starts_at - today_start))
    events = session.scalars(
        select(CalendarEvent)
        .where(_all_words(query, CalendarEvent.title, func.coalesce(CalendarEvent.location, "")))
        .order_by(case((upcoming, 0), else_=1), seconds_away)
        .limit(limit)
    )

    mails = session.scalars(
        select(Email)
        .where(
            Email.removed_at.is_(None),
            _all_words(
                query,
                Email.subject,
                Email.from_addr,
                func.coalesce(Email.from_name, ""),
                func.coalesce(Email.summary, ""),
            ),
        )
        .order_by(Email.received_at.desc())
        .limit(limit)
    )

    return Results(
        tasks=list(tasks),
        notes=note_service.search(session, query, limit=limit),
        events=list(events),
        mails=list(mails),
    )
