"""Tools for tasks, areas and the day overview."""

from datetime import date, timedelta
from datetime import time as dtime
from typing import Annotated, Any

from mcp.server.mcpserver.exceptions import ToolError
from pydantic import Field
from sqlalchemy import select

from app.mcp.core import IDEMPOTENT_WRITE, READ, WRITE, mcp
from app.mcp.db import session_scope
from app.mcp.guards import area_id_for, audited, require_task
from app.mcp.schemas import (
    AreaOut,
    ClearableField,
    CompletedOut,
    CompletedTaskOut,
    CompleteOut,
    DeadlinesOut,
    EventOut,
    PriorityName,
    StatusName,
    TaskDetail,
    TaskList,
    TaskOut,
    TodayOut,
    event_out,
    task_out,
)
from app.models.tasks import Task, TaskPriority, TaskSource, TaskStatus
from app.schemas.tasks import TaskCreate, TaskUpdate
from app.services import analysis
from app.services import tasks as task_service
from app.services.clock import local_today, local_tz


@mcp.tool(title="Today", annotations=READ)
def get_today() -> TodayOut:
    """Get the user's day: overdue tasks, tasks due today, tasks planned for today,
    deadlines in the next 7 days, what was completed today, today's events, and tomorrow's first
    event with the latest bedtime tonight."""
    with session_scope() as session:
        o = task_service.today_overview(session)
        return TodayOut(
            today=o.today,
            overdue=[task_out(t) for t in o.overdue],
            due_today=[task_out(t) for t in o.due_today],
            scheduled=[task_out(t) for t in o.scheduled],
            upcoming=[task_out(t) for t in o.upcoming],
            done_today=[task_out(t) for t in o.done_today],
            events=[event_out(e) for e in o.events],
            tomorrow_first_event=(
                f"{bed.first_event_at:%H:%M} {bed.title}"
                if (bed := analysis.bedtime_for(session, o.today + timedelta(days=1)))
                else None
            ),
            tomorrow_latest_bedtime=f"{bed.latest_bedtime:%H:%M}" if bed else None,
            tomorrow_bedtime_capped=bed.capped if bed else False,
        )


@mcp.tool(title="List tasks", annotations=READ)
def list_tasks(
    status: Annotated[
        list[StatusName] | None, Field(description="Default: open and in_progress")
    ] = None,
    area: Annotated[str | None, Field(description="Area slug, see list_areas")] = None,
    query: Annotated[str | None, Field(description="Text search in title and notes")] = None,
    limit: Annotated[int, Field(ge=1, le=200)] = 50,
) -> TaskList:
    """List tasks, sorted by date and priority. Filter by status, area or text."""
    with session_scope() as session:
        found = task_service.list_tasks(
            session,
            status=[TaskStatus(s) for s in status] if status else None,
            area_id=area_id_for(session, area),
            query=query,
        )
        return TaskList(
            count=len(found),
            truncated=len(found) > limit,
            tasks=[task_out(t) for t in found[:limit]],
        )


@mcp.tool(title="Deadlines", annotations=READ)
def get_deadlines(
    days: Annotated[int, Field(ge=1, le=365, description="How far ahead to look")] = 14,
) -> DeadlinesOut:
    """Open tasks with a deadline: everything overdue plus deadlines in the next `days` days."""
    today = local_today()
    with session_scope() as session:
        found = task_service.list_tasks(session, due_before=today + timedelta(days=days))
        with_deadline = [t for t in found if t.due_date is not None]
        return DeadlinesOut(
            today=today,
            overdue=[task_out(t) for t in with_deadline if t.due_date < today],
            upcoming=[task_out(t) for t in with_deadline if t.due_date >= today],
        )


@mcp.tool(title="Completed tasks", annotations=READ)
def completed_tasks(
    days: Annotated[int, Field(ge=1, le=90, description="How many days back, today included")] = 7,
    area: Annotated[str | None, Field(description="Area slug, see list_areas")] = None,
) -> CompletedOut:
    """What the user got done: tasks completed in the last `days` days with the time of
    completion, the last one first, and the count per day. Use it for a weekly review or when
    the user asks what they did."""
    today = local_today()
    since = today - timedelta(days=days - 1)
    tz = local_tz()
    with session_scope() as session:
        found = task_service.completed_since(session, since, area_id_for(session, area))
        by_day: dict[str, int] = {}
        tasks = []
        for t in found:
            at = t.completed_at.astimezone(tz)
            by_day[at.date().isoformat()] = by_day.get(at.date().isoformat(), 0) + 1
            tasks.append(
                CompletedTaskOut(
                    **task_out(t).model_dump(), completed=at.strftime("%Y-%m-%d %H:%M")
                )
            )
        return CompletedOut(since=since, until=today, count=len(tasks), by_day=by_day, tasks=tasks)


@mcp.tool(title="Task details", annotations=READ)
def get_task(task_id: int) -> TaskDetail:
    """Get one task with its change history."""
    with session_scope() as session:
        task = require_task(session, task_id)
        history = [
            EventOut(type=e.type, actor=e.actor, at=e.created_at.isoformat(), changes=e.payload)
            for e in task.events
        ]
        return TaskDetail(**task_out(task).model_dump(), history=history)


@mcp.tool(title="List areas", annotations=READ)
def list_areas() -> list[AreaOut]:
    """List the areas tasks can belong to (slug and display name)."""
    with session_scope() as session:
        return [AreaOut(slug=a.slug, name=a.name) for a in task_service.list_areas(session)]


@mcp.tool(title="Add task", annotations=WRITE)
def add_task(
    title: Annotated[str, Field(min_length=1, max_length=500)],
    due_date: Annotated[date | None, Field(description="Deadline, YYYY-MM-DD")] = None,
    due_time: Annotated[dtime | None, Field(description="HH:MM, needs due_date")] = None,
    scheduled_date: Annotated[
        date | None, Field(description="Day to work on it, YYYY-MM-DD")
    ] = None,
    area: Annotated[str | None, Field(description="Area slug, see list_areas")] = None,
    priority: PriorityName = "normal",
    tags: list[str] | None = None,
    notes: str | None = None,
    recurrence: Annotated[
        str | None, Field(description="RRULE without prefix, e.g. FREQ=WEEKLY;BYDAY=MO")
    ] = None,
) -> TaskOut:
    """Create a task. Prefer this over quick_add when you already know the fields."""
    if due_time and not due_date:
        raise ToolError("due_time needs a due_date.")
    with audited("add_task", locals()) as session:
        task = task_service.create_task(
            session,
            TaskCreate(
                title=title,
                due_date=due_date,
                due_time=due_time,
                scheduled_date=scheduled_date,
                area_id=area_id_for(session, area),
                priority=TaskPriority(priority),
                tags=tags or [],
                notes=notes,
                recurrence=recurrence,
                source=TaskSource.claude,
            ),
            actor="claude",
        )
        return task_out(task)


@mcp.tool(title="Quick add", annotations=WRITE)
def quick_add(
    text: Annotated[
        str,
        Field(
            min_length=1,
            max_length=1000,
            description='Shorthand, e.g. "morgen 14 Uhr Blatt 3 abgeben #study !hoch"',
        ),
    ],
) -> TaskOut:
    """Create a task from the user's quick-add shorthand (German or English): dates, @planned
    day, times, #area, !priority and recurrence like "jeden Montag" / "every monday"."""
    with audited("quick_add", {"text": text}) as session:
        task = task_service.quick_add(session, text, actor="claude", source=TaskSource.claude)
        return task_out(task)


@mcp.tool(title="Update task", annotations=IDEMPOTENT_WRITE)
def update_task(
    task_id: int,
    title: Annotated[str | None, Field(min_length=1, max_length=500)] = None,
    status: Annotated[
        StatusName | None, Field(description='"cancelled" drops the task (the undo)')
    ] = None,
    priority: PriorityName | None = None,
    area: Annotated[str | None, Field(description="Area slug")] = None,
    tags: Annotated[list[str] | None, Field(description="Replaces all tags")] = None,
    due_date: date | None = None,
    due_time: dtime | None = None,
    scheduled_date: date | None = None,
    recurrence: str | None = None,
    notes: Annotated[str | None, Field(description="Replaces the notes")] = None,
    clear: Annotated[
        list[ClearableField] | None, Field(description="Fields to empty, e.g. ['due_date']")
    ] = None,
) -> TaskOut:
    """Change fields of a task. Only the given fields change; use `clear` to empty a field."""
    with audited("update_task", locals()) as session:
        task = require_task(session, task_id)
        changes: dict[str, Any] = {
            k: v
            for k, v in {
                "title": title,
                "status": status,
                "priority": priority,
                "tags": tags,
                "due_date": due_date,
                "due_time": due_time,
                "scheduled_date": scheduled_date,
                "recurrence": recurrence,
                "notes": notes,
            }.items()
            if v is not None
        }
        if area is not None:
            changes["area_id"] = area_id_for(session, area)
        for field in clear or []:
            changes["area_id" if field == "area" else field] = [] if field == "tags" else None
        if not changes:
            raise ToolError("Nothing to change. Pass at least one field or `clear`.")
        task_service.update_task(session, task, TaskUpdate(**changes), actor="claude")
        return task_out(task)


@mcp.tool(title="Add task note", annotations=WRITE)
def add_task_note(
    task_id: int,
    text: Annotated[
        str,
        Field(
            min_length=1, max_length=4000, description="e.g. where the work stands, what is next"
        ),
    ],
) -> TaskOut:
    """Add a paragraph with today's date at the end of a task's notes, without changing what
    is already there. Prefer this over update_task(notes=...) for progress, decisions and next
    steps: update_task replaces the notes."""
    with audited("add_task_note", {"task_id": task_id, "chars": len(text)}) as session:
        task = require_task(session, task_id)
        task_service.append_note(session, task, text, actor="claude")
        return task_out(task)


@mcp.tool(title="Complete task", annotations=IDEMPOTENT_WRITE)
def complete_task(task_id: int) -> CompleteOut:
    """Mark a task as done. For a repeating task the next instance is created and returned."""
    with audited("complete_task", {"task_id": task_id}) as session:
        task = require_task(session, task_id)
        task_service.set_status(session, task, TaskStatus.done, actor="claude")
        follow_up = session.scalar(select(Task).where(Task.recurrence_parent_id == task.id))
        return CompleteOut(
            task=task_out(task), next_instance=task_out(follow_up) if follow_up else None
        )
