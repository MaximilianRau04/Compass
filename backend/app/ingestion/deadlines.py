"""Deadlines from calendar feeds, kept in sync as tasks.

Learning platforms put assignment deadlines into their calendar feed, e.g. ILIAS as an entry titled
"<assignment> (Abgabetermin)". Which entries of a feed are deadlines is set per feed
(Settings.deadline_patterns). Rules (see the sync rules for tasks):

- (source, external_id) is unique, so a sync never creates duplicates.
- The sync only owns title, due_date and due_time. Area, priority, tags, scheduled_date,
  notes and status stay as the user set them (the area and notes are only set on creation).
- A changed deadline updates the task and is recorded as a task event.
- A future deadline that disappears from the feed cancels the task instead of deleting it.
  If it shows up again, the task is reopened.
"""

import re
from collections import Counter
from datetime import date, time
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.tasks import Area, Task, TaskSource, TaskStatus
from app.schemas.tasks import TaskCreate
from app.services import tasks as task_service
from app.services.clock import local_tz

if TYPE_CHECKING:
    from app.ingestion.calendar import ParsedEvent

REMOVED = "removed_from_source"
MAX_NOTES = 1000


def clean_title(title: str, pattern: re.Pattern) -> str:
    return pattern.sub("", title).strip() or title


def _source(feed: str) -> TaskSource:
    """ILIAS has its own source; the tasks of all other feeds tell them apart by their id."""
    return TaskSource.ilias if feed == "ilias" else TaskSource.feed


def _prefix(feed: str) -> str:
    return "" if feed == "ilias" else f"{feed}:"


def _due(event: "ParsedEvent") -> tuple[date, time | None]:
    local = event.starts_at.astimezone(local_tz())
    if event.all_day:
        return local.date(), None
    return local.date(), local.time().replace(second=0, microsecond=0)


def _keys(feed: str, events: list["ParsedEvent"]) -> dict[str, "ParsedEvent"]:
    """External id per deadline: the UID, plus the date for the rare recurring entry."""
    per_uid = Counter(e.uid for e in events)
    keys = {}
    for event in events:
        key = event.uid
        if per_uid[event.uid] > 1:
            key = f"{event.uid}@{_due(event)[0].isoformat()}"
        keys[f"{_prefix(feed)}{key}"[:200]] = event
    return keys


def _removed_by_sync(task: Task, feed: str) -> bool:
    status_events = [
        e for e in task.events if e.type in ("cancelled", "reopened", "completed", "status_changed")
    ]
    if not status_events:
        return False
    last = status_events[-1]
    return last.type == "cancelled" and last.actor == feed and last.payload.get("reason") == REMOVED


def _default_area_id(session: Session, feed: str) -> int | None:
    settings = get_settings()
    slug = settings.ilias_deadline_area.strip().lower() if feed == "ilias" else ""
    slug = slug or settings.calendar_area_map.get(feed, "")
    if not slug:
        return None
    return session.scalar(select(Area.id).where(Area.slug == slug))


def sync_deadlines(
    session: Session,
    feed: str,
    events: list["ParsedEvent"],
    pattern: re.Pattern,
    today: date,
    window_end: date,
) -> dict:
    source = _source(feed)
    deadlines = {k: e for k, e in _keys(feed, events).items() if _due(e)[0] >= today}
    existing = {
        t.external_id: t
        for t in session.scalars(
            select(Task).where(
                Task.source == source, Task.external_id.startswith(_prefix(feed), autoescape=True)
            )
        ).unique()
    }
    area_id = _default_area_id(session, feed)
    stats = {"created": 0, "updated": 0, "cancelled": 0, "reopened": 0}

    for key, event in deadlines.items():
        title = clean_title(event.title, pattern)
        due_date, due_time = _due(event)
        task = existing.get(key)
        if task is None:
            notes = event.description[:MAX_NOTES] if event.description else None
            task_service.create_task(
                session,
                TaskCreate(
                    title=title,
                    due_date=due_date,
                    due_time=due_time,
                    area_id=area_id,
                    notes=notes,
                    source=source,
                    external_id=key,
                ),
                actor=feed,
            )
            stats["created"] += 1
            continue

        owned = {"title": title, "due_date": due_date, "due_time": due_time}
        if task_service.sync_fields(session, task, owned, feed):
            stats["updated"] += 1
        if task.status == TaskStatus.cancelled and _removed_by_sync(task, feed):
            task_service.set_status(
                session, task, TaskStatus.open, feed, {"reason": "back_in_source"}
            )
            stats["reopened"] += 1

    # Only future deadlines can disappear; past ones drop out of the window by themselves.
    for key, task in existing.items():
        if key in deadlines or task.status not in task_service.ACTIVE:
            continue
        if task.due_date is not None and today <= task.due_date < window_end:
            task_service.set_status(session, task, TaskStatus.cancelled, feed, {"reason": REMOVED})
            stats["cancelled"] += 1

    session.flush()
    return stats
