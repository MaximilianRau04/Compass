"""Tools for briefs on the dashboard and push notifications."""

from datetime import date
from typing import Annotated

from mcp.server.mcpserver.exceptions import ToolError
from pydantic import Field

from app.mcp.core import IDEMPOTENT_WRITE, READ, WRITE, mcp
from app.mcp.db import session_scope
from app.mcp.guards import audited, caller
from app.mcp.schemas import BriefOut, NotificationOut, brief_out
from app.services import briefs, push
from app.services.clock import utc_now


@mcp.tool(title="Save brief", annotations=IDEMPOTENT_WRITE)
def save_brief(
    body: Annotated[
        str,
        Field(
            min_length=1,
            max_length=briefs.MAX_BODY,
            description="Markdown: ## headings, - lists, **bold**, [text](https://...) links",
        ),
    ],
    kind: Annotated[
        str,
        Field(
            pattern=briefs.KIND.pattern,
            description='"daily" (daily brief), "news" (news report), "weekly", or a short slug',
        ),
    ] = "daily",
    title: Annotated[str | None, Field(max_length=200)] = None,
    day: Annotated[date | None, Field(description="YYYY-MM-DD, default today")] = None,
) -> BriefOut:
    """Store a text on the Compass dashboard: the daily brief, a news report or the output of
    another routine. Saving the same kind for the same day replaces the earlier text."""
    with audited("save_brief", {"kind": kind, "day": day, "chars": len(body)}) as session:
        return brief_out(briefs.save(session, kind, body, title, day, actor=caller()))


@mcp.tool(title="Send notification", annotations=WRITE)
def send_notification(
    title: Annotated[str, Field(min_length=1, max_length=80)],
    body: Annotated[str, Field(min_length=1, max_length=300)],
    path: Annotated[
        str,
        Field(
            pattern=r"^/[a-z0-9/_-]*$",
            description='Compass page opened on tap, e.g. "/" (today), "/tasks", "/news"',
        ),
    ] = "/",
) -> NotificationOut:
    """Push a short notification to the user's phone, e.g. "Daily brief is ready" at the end of a
    routine. Use it sparingly, for things the user wants to know now; the text goes to the lock
    screen."""
    if not push.enabled():
        raise ToolError("Push is not set up on the server (VAPID keys missing).")
    with audited("send_notification", {"title": title, "path": path}) as session:
        key = f"claude:{utc_now().isoformat()}"
        message = push.Message(title=title, body=body, url=path, ttl=12 * 3600)
        return NotificationOut(devices=push.send(session, "claude", key, message))


@mcp.tool(title="Get brief", annotations=READ)
def get_brief(
    kind: Annotated[str, Field(pattern=briefs.KIND.pattern)] = "daily",
    day: Annotated[date | None, Field(description="Default: the newest one")] = None,
) -> BriefOut:
    """Read a saved brief: the newest of a kind, or the one of a given day."""
    with session_scope() as session:
        if day:
            found = briefs.recent(session, kind, 60)
            brief = next((b for b in found if b.local_date == day), None)
        else:
            brief = briefs.latest(session, kind)
        if brief is None:
            raise ToolError(f"No {kind!r} brief saved" + (f" for {day}." if day else " yet."))
        return brief_out(brief)
