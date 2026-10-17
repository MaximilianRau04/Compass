"""ILIAS exercise deadlines from the ILIAS calendar feed, kept in sync as tasks.

ILIAS puts each assignment deadline into the personal calendar as an entry titled
"<assignment> (Abgabetermin)". Rules (see the sync rules for tasks):

- (source, external_id) is unique, so a sync never creates duplicates.
- The sync only owns title, due_date and due_time. Area, priority, tags, scheduled_date,
  notes and status stay as the user set them (the area and notes are only set on creation).
- A changed deadline updates the task and is recorded as a task event.
- A future deadline that disappears from the feed cancels the task instead of deleting it.
  If it shows up again, the task is reopened.
"""

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

ACTOR = "ilias"
REMOVED = "removed_from_source"
MAX_NOTES = 1000


def _suffixes() -> list[str]:
    return [s.strip() for s in get_settings().ilias_deadline_suffixes.split(",") if s.strip()]


def is_deadline(title: str) -> bool:
    return any(title.endswith(suffix) for suffix in _suffixes())


def clean_title(title: str) -> str:
    for suffix in _suffixes():
        if title.endswith(suffix):
            return title.removesuffix(suffix).strip() or title
    return title


def _due(event: "ParsedEvent") -> tuple[date, time | None]:
    local = event.starts_at.astimezone(local_tz())
    if event.all_day:
        return local.date(), None
    return local.date(), local.time().replace(second=0, microsecond=0)


def _keys(events: list["ParsedEvent"]) -> dict[str, "ParsedEvent"]:
    """External id per deadline: the UID, plus the date for the rare recurring entry."""
    per_uid = Counter(e.uid for e in events)
    keys = {}
    for event in events:
        key = event.uid
        if per_uid[event.uid] > 1:
            key = f"{event.uid}@{_due(event)[0].isoformat()}"
        keys[key[:200]] = event
    return keys


def _removed_by_sync(task: Task) -> bool:
    status_events = [
        e for e in task.events if e.type in ("cancelled", "reopened", "completed", "status_changed")
    ]
    if not status_events:
        return False
    last = status_events[-1]
    return (
        last.type == "cancelled" and last.actor == ACTOR and last.payload.get("reason") == REMOVED
    )


def _default_area_id(session: Session) -> int | None:
    slug = get_settings().ilias_deadline_area.strip().lower()
    if not slug:
        return None
    return session.scalar(select(Area.id).where(Area.slug == slug))


def sync_deadlines(
    session: Session, events: list["ParsedEvent"], today: date, window_end: date
) -> dict:
    deadlines = {k: e for k, e in _keys(events).items() if _due(e)[0] >= today}
    existing = {
        t.external_id: t
        for t in session.scalars(
            select(Task).where(Task.source == TaskSource.ilias, Task.external_id.is_not(None))
        ).unique()
    }
    area_id = _default_area_id(session)
    stats = {"created": 0, "updated": 0, "cancelled": 0, "reopened": 0}

    for key, event in deadlines.items():
        title = clean_title(event.title)
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
                    source=TaskSource.ilias,
                    external_id=key,
                ),
                actor=ACTOR,
            )
            stats["created"] += 1
            continue

        owned = {"title": title, "due_date": due_date, "due_time": due_time}
        if task_service.sync_fields(session, task, owned, ACTOR):
            stats["updated"] += 1
        if task.status == TaskStatus.cancelled and _removed_by_sync(task):
            task_service.set_status(
                session, task, TaskStatus.open, ACTOR, {"reason": "back_in_source"}
            )
            stats["reopened"] += 1

    # Only future deadlines can disappear; past ones drop out of the window by themselves.
    for key, task in existing.items():
        if key in deadlines or task.status not in task_service.ACTIVE:
            continue
        if task.due_date is not None and today <= task.due_date < window_end:
            task_service.set_status(session, task, TaskStatus.cancelled, ACTOR, {"reason": REMOVED})
            stats["cancelled"] += 1

    session.flush()
    return stats
