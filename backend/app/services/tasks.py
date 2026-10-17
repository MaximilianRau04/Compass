"""Task logic shared by the REST API and (later) the MCP server."""

from collections.abc import Sequence
from datetime import date, datetime, time, timedelta
from typing import Any

from sqlalchemy import Select, and_, func, or_, select
from sqlalchemy.orm import Session

from app.models.tasks import Area, Task, TaskEvent, TaskPriority, TaskSource, TaskStatus
from app.schemas.tasks import QuickAddPreview, TaskCreate, TaskUpdate, TodayOverview
from app.services.calendar import events_between
from app.services.clock import local_today, local_tz, utc_now
from app.services.quick_add import parse_quick_add
from app.services.recurrence import next_occurrence

ACTIVE = (TaskStatus.open, TaskStatus.in_progress)
PRIORITY_RANK = {
    TaskPriority.urgent: 0,
    TaskPriority.high: 1,
    TaskPriority.normal: 2,
    TaskPriority.low: 3,
}


class TaskError(ValueError):
    pass


def _jsonable(value: Any) -> Any:
    if isinstance(value, date | time | datetime):
        return value.isoformat()
    if isinstance(value, list):
        return [_jsonable(v) for v in value]
    return value.value if hasattr(value, "value") else value


def _event(session: Session, task: Task, type_: str, actor: str, payload: dict | None = None):
    session.add(TaskEvent(task=task, type=type_, actor=actor, payload=payload or {}))


def _sorted(tasks: Sequence[Task]) -> list[Task]:
    far = date.max
    return sorted(
        tasks,
        key=lambda t: (
            t.due_date or t.scheduled_date or far,
            t.due_time or time.max,
            PRIORITY_RANK[t.priority],
            t.sort_order,
            t.id,
        ),
    )


# --- Areas ---------------------------------------------------------------------------------


def list_areas(session: Session, include_archived: bool = False) -> list[Area]:
    stmt = select(Area).order_by(Area.sort_order, Area.name)
    if not include_archived:
        stmt = stmt.where(Area.archived.is_(False))
    return list(session.scalars(stmt))


def area_lookup(session: Session) -> dict[str, str]:
    """Lowercase slug and name -> slug, for the quick-add parser."""
    lookup: dict[str, str] = {}
    for area in list_areas(session):
        lookup[area.slug.lower()] = area.slug
        lookup[area.name.lower().replace(" ", "-")] = area.slug
    return lookup


# --- Queries -------------------------------------------------------------------------------


def list_tasks(
    session: Session,
    *,
    status: Sequence[TaskStatus] | None = None,
    area_id: int | None = None,
    query: str | None = None,
    due_before: date | None = None,
    limit: int = 500,
) -> list[Task]:
    stmt: Select = select(Task)
    stmt = stmt.where(Task.status.in_(status or ACTIVE))
    if area_id is not None:
        stmt = stmt.where(Task.area_id == area_id)
    if query:
        like = f"%{query}%"
        stmt = stmt.where(or_(Task.title.ilike(like), Task.notes.ilike(like)))
    if due_before is not None:
        stmt = stmt.where(Task.due_date <= due_before)
    stmt = stmt.order_by(Task.updated_at.desc()).limit(limit)
    return _sorted(session.scalars(stmt).unique().all())


def today_overview(session: Session, today: date | None = None) -> TodayOverview:
    today = today or local_today()
    active = Task.status.in_(ACTIVE)

    overdue = session.scalars(select(Task).where(active, Task.due_date < today)).unique().all()
    due_today = session.scalars(select(Task).where(active, Task.due_date == today)).unique().all()
    scheduled = (
        session.scalars(
            select(Task).where(
                active,
                Task.scheduled_date <= today,
                or_(Task.due_date.is_(None), Task.due_date > today),
            )
        )
        .unique()
        .all()
    )
    upcoming = (
        session.scalars(
            select(Task).where(
                active,
                Task.due_date > today,
                Task.due_date <= today + timedelta(days=7),
                or_(Task.scheduled_date.is_(None), Task.scheduled_date > today),
            )
        )
        .unique()
        .all()
    )
    start = datetime.combine(today, time.min, tzinfo=local_tz())
    done_today = (
        session.scalars(
            select(Task).where(
                Task.status == TaskStatus.done,
                and_(Task.completed_at >= start, Task.completed_at < start + timedelta(days=1)),
            )
        )
        .unique()
        .all()
    )
    return TodayOverview.model_validate(
        {
            "today": today,
            "overdue": _sorted(overdue),
            "due_today": _sorted(due_today),
            "scheduled": _sorted(scheduled),
            "upcoming": _sorted(upcoming),
            "done_today": sorted(done_today, key=lambda t: t.completed_at or start),
            "events": events_between(session, today, today + timedelta(days=1)),
        },
        from_attributes=True,
    )


def get_task(session: Session, task_id: int) -> Task | None:
    return session.get(Task, task_id)


# --- Mutations -----------------------------------------------------------------------------


def _check_area(session: Session, area_id: int | None) -> None:
    if area_id is not None and session.get(Area, area_id) is None:
        raise TaskError(f"area {area_id} does not exist")


def create_task(
    session: Session, data: TaskCreate, actor: str = "web", extra: dict | None = None
) -> Task:
    _check_area(session, data.area_id)
    task = Task(**data.model_dump())
    if task.status == TaskStatus.done:
        task.completed_at = utc_now()
    session.add(task)
    session.flush()
    _event(session, task, "created", actor, {"source": task.source.value, **(extra or {})})
    return task


def update_task(session: Session, task: Task, data: TaskUpdate, actor: str = "web") -> Task:
    changes = data.model_dump(exclude_unset=True)
    if "area_id" in changes:
        _check_area(session, changes["area_id"])
    if changes.get("title") is None:
        changes.pop("title", None)

    new_status = changes.pop("status", None)
    diff = {}
    for field, value in changes.items():
        old = getattr(task, field)
        if old != value:
            diff[field] = {"from": _jsonable(old), "to": _jsonable(value)}
            setattr(task, field, value)
    if diff:
        _event(session, task, "updated", actor, diff)

    if new_status is not None and new_status != task.status:
        set_status(session, task, new_status, actor)
    session.flush()
    return task


def sync_fields(session: Session, task: Task, fields: dict[str, Any], actor: str) -> bool:
    """Set fields owned by an external source (e.g. an ILIAS deadline). Records the changes as
    one "synced" event. Returns whether anything changed."""
    diff = {}
    for field, value in fields.items():
        old = getattr(task, field)
        if old != value:
            diff[field] = {"from": _jsonable(old), "to": _jsonable(value)}
            setattr(task, field, value)
    if diff:
        _event(session, task, "synced", actor, diff)
    return bool(diff)


def set_status(
    session: Session,
    task: Task,
    status: TaskStatus,
    actor: str = "web",
    extra: dict | None = None,
) -> Task:
    previous = task.status
    if previous == status:
        return task
    task.status = status
    if status == TaskStatus.done:
        task.completed_at = utc_now()
        _event(session, task, "completed", actor, extra)
        _spawn_next(session, task, actor)
    else:
        task.completed_at = None
        type_ = {TaskStatus.cancelled: "cancelled"}.get(status, "reopened")
        if previous in ACTIVE and status in ACTIVE:
            type_ = "status_changed"
        payload = {"from": previous.value, "to": status.value, **(extra or {})}
        _event(session, task, type_, actor, payload)
    session.flush()
    return task


def _spawn_next(session: Session, task: Task, actor: str) -> Task | None:
    """Create the next instance of a recurring task. Returns None if not recurring."""
    if not task.recurrence:
        return None
    # Only one follow-up per instance, even if the task is reopened and completed again.
    exists = session.scalar(
        select(func.count()).select_from(Task).where(Task.recurrence_parent_id == task.id)
    )
    if exists:
        return None

    today = local_today()
    anchor = task.scheduled_date or task.due_date or today
    nxt = next_occurrence(task.recurrence, anchor, today)
    if nxt is None:
        return None
    shift = nxt - anchor

    follow_up = Task(
        title=task.title,
        notes=task.notes,
        area_id=task.area_id,
        tags=list(task.tags),
        priority=task.priority,
        status=TaskStatus.open,
        due_date=task.due_date + shift if task.due_date else None,
        due_time=task.due_time,
        scheduled_date=task.scheduled_date + shift if task.scheduled_date else None,
        recurrence=task.recurrence,
        recurrence_parent_id=task.id,
        source=task.source,
    )
    if follow_up.due_date is None and follow_up.scheduled_date is None:
        follow_up.scheduled_date = nxt
    session.add(follow_up)
    session.flush()
    _event(session, follow_up, "created", actor, {"recurrence_of": task.id})
    return follow_up


# --- Quick add -----------------------------------------------------------------------------


def preview_quick_add(session: Session, text: str, today: date | None = None) -> QuickAddPreview:
    parsed = parse_quick_add(text, today or local_today(), area_lookup(session))
    area = (
        session.scalar(select(Area).where(Area.slug == parsed.area_slug))
        if parsed.area_slug
        else None
    )
    return QuickAddPreview.model_validate({**parsed.__dict__, "area": area}, from_attributes=True)


def quick_add(
    session: Session,
    text: str,
    actor: str = "web",
    today: date | None = None,
    source: TaskSource = TaskSource.manual,
) -> Task:
    preview = preview_quick_add(session, text, today)
    if not preview.title:
        raise TaskError("title is empty after parsing")
    data = TaskCreate(
        title=preview.title,
        area_id=preview.area.id if preview.area else None,
        tags=preview.tags,
        priority=preview.priority or TaskPriority.normal,
        due_date=preview.due_date,
        due_time=preview.due_time,
        scheduled_date=preview.scheduled_date,
        recurrence=preview.recurrence,
        source=source,
    )
    return create_task(session, data, actor, extra={"quick_add": text})
