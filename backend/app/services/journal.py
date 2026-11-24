"""The journal: one entry per day with mood and energy (1 to 5) and a free text. The daily page
bundles it with what the day held: the brief, tasks done, training, the night and the food."""

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.journal import JournalEntry
from app.models.news import Brief
from app.models.notes import Note
from app.models.tasks import Task, TaskStatus
from app.services import daily, embeddings
from app.services.clock import local_today, local_tz
from app.services.notes import snippet
from app.services.tasks import contains

MAX_TEXT = 20_000


class JournalError(ValueError):
    pass


def _check_scale(name: str, value: int | None) -> None:
    if value is not None and not 1 <= value <= 5:
        raise JournalError(f"{name} goes from 1 to 5")


def get(session: Session, day: date) -> JournalEntry | None:
    return session.get(JournalEntry, day)


# Marks a field that is not given and keeps its value; None clears mood or energy.
KEEP: Any = object()


def save(
    session: Session,
    day: date | None,
    mood: int | None = KEEP,
    energy: int | None = KEEP,
    text: str | None = KEEP,
    append: bool = False,
) -> JournalEntry | None:
    """Set the given fields of a day; fields left out keep their value, None clears mood or
    energy. With append, the text is added as a new paragraph instead of replacing it. A day left
    without mood, energy and text has no entry: it is removed, or not created, and None returned."""
    day = day or local_today()
    if day > local_today():
        raise JournalError("the day lies in the future")
    entry = get(session, day)
    new_mood = entry.mood if entry else None
    new_energy = entry.energy if entry else None
    new_text = entry.text if entry else ""
    if mood is not KEEP:
        _check_scale("mood", mood)
        new_mood = mood
    if energy is not KEEP:
        _check_scale("energy", energy)
        new_energy = energy
    if text is not KEEP:
        text = (text or "").strip()
        if append and new_text and text:
            text = f"{new_text.rstrip()}\n\n{text}"
        elif append and not text:
            text = new_text
        if len(text) > MAX_TEXT:
            raise JournalError(f"the text is longer than {MAX_TEXT} characters")
        new_text = text
    if new_mood is None and new_energy is None and not new_text:
        if entry is not None:
            session.delete(entry)
            session.flush()
        return None
    if entry is None:
        entry = JournalEntry(local_date=day)
        session.add(entry)
    text_changed = entry.text != new_text
    entry.mood, entry.energy, entry.text = new_mood, new_energy, new_text
    if text_changed:
        embeddings.embed_journal(entry)
    session.flush()
    return entry


def entries(session: Session, since: date, until: date) -> list[JournalEntry]:
    """Newest first."""
    return list(
        session.scalars(
            select(JournalEntry)
            .where(JournalEntry.local_date >= since, JournalEntry.local_date <= until)
            .order_by(JournalEntry.local_date.desc())
        )
    )


@dataclass
class Found:
    entry: JournalEntry
    snippet: str


def search(session: Session, query: str, limit: int = 8) -> list[Found]:
    """Entries whose text holds every word of the query, newest first. With embeddings set up,
    the rest are filled with entries that mean something alike in other words."""
    query = " ".join(query.split())
    if not query:
        return []
    words = [JournalEntry.text.ilike(contains(word), escape="\\") for word in query.split()]
    found = list(
        session.scalars(
            select(JournalEntry).where(*words).order_by(JournalEntry.local_date.desc()).limit(limit)
        )
    )
    if len(found) < limit and embeddings.configured():
        vec = embeddings.embed_query(query)
        if vec is not None:
            rest = select(JournalEntry).where(
                JournalEntry.local_date.notin_([e.local_date for e in found])
            )
            found += session.scalars(
                embeddings.nearest(rest, JournalEntry.embedding, vec).limit(limit - len(found))
            )
    return [Found(entry=e, snippet=snippet(e.text, query)) for e in found]


@dataclass
class Day:
    date: date
    entry: JournalEntry | None
    row: daily.DayRow
    briefs: list[tuple[str, str | None, str]] = field(default_factory=list)  # kind, title, body
    tasks_done: list[str] = field(default_factory=list)
    notes: list[tuple[int, str]] = field(default_factory=list)  # id, title


def day(session: Session, when: date) -> Day:
    tz = local_tz()
    [row] = daily.daily_rows(session, 1, when)
    briefs = [
        (b.kind, b.title, b.body)
        for b in session.scalars(select(Brief).where(Brief.local_date == when).order_by(Brief.kind))
    ]
    start = datetime.combine(when, time.min, tzinfo=tz)
    end = start + timedelta(days=1)
    done = list(
        session.scalars(
            select(Task.title)
            .where(
                Task.status == TaskStatus.done,
                Task.completed_at >= start,
                Task.completed_at < end,
            )
            .order_by(Task.completed_at)
        )
    )
    notes = [
        (n.id, n.title)
        for n in session.scalars(
            select(Note)
            .where(
                Note.archived_at.is_(None),
                or_(
                    (Note.created_at >= start) & (Note.created_at < end),
                    (Note.updated_at >= start) & (Note.updated_at < end),
                ),
            )
            .order_by(Note.updated_at.desc())
        )
    ]
    return Day(
        date=when, entry=get(session, when), row=row, briefs=briefs, tasks_done=done, notes=notes
    )
