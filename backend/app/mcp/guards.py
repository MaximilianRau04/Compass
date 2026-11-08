"""Shared checks of the write tools: rate limit, audit log, and lookups that turn a
missing task or area into a ToolError the assistant can act on."""

import time
from collections import defaultdict, deque
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date
from datetime import time as dtime
from typing import Any

from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.mcp.db import session_scope
from app.models.oauth import AuditLog
from app.models.tasks import Task
from app.services import tasks as task_service
from app.services.notes import NoteError
from app.services.tasks import TaskError

_writes: dict[str, deque[float]] = defaultdict(deque)


def caller() -> str:
    token = get_access_token()
    return f"mcp:{token.client_id}" if token else "mcp:local"


@contextmanager
def audited(action: str, arguments: dict[str, Any]) -> Iterator[Session]:
    """Rate limit, run a write in a session, and record the outcome in the audit log."""
    actor = caller()
    window = _writes[actor]
    now = time.monotonic()
    while window and window[0] < now - 3600:
        window.popleft()
    if len(window) >= get_settings().mcp_write_limit_per_hour:
        raise ToolError("Write limit reached for this hour. Try again later.")
    window.append(now)

    args = {k: (v.isoformat() if isinstance(v, date | dtime) else v) for k, v in arguments.items()}
    try:
        with session_scope() as session:
            yield session
    except Exception as exc:
        with session_scope() as log:
            log.add(AuditLog(actor=actor, action=action, arguments=args, ok=False, detail=str(exc)))
        if isinstance(exc, ToolError):
            raise
        if isinstance(exc, TaskError | NoteError | ValidationError | ValueError):
            raise ToolError(str(exc)) from exc
        raise
    else:
        with session_scope() as log:
            log.add(AuditLog(actor=actor, action=action, arguments=args, ok=True))


def require_task(session: Session, task_id: int) -> Task:
    task = task_service.get_task(session, task_id)
    if task is None:
        raise ToolError(f"No task with id {task_id}. Use list_tasks to find the right id.")
    return task


def area_id_for(session: Session, slug: str | None) -> int | None:
    if slug is None:
        return None
    area = task_service.find_area(session, slug.lower().lstrip("#"))
    if area is None:
        slugs = ", ".join(a.slug for a in task_service.list_areas(session))
        raise ToolError(f"Unknown area {slug!r}. Valid areas: {slugs}.")
    return area.id
