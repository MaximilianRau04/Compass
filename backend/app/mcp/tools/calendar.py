"""Tools for the calendar."""

from datetime import date, timedelta
from typing import Annotated

from pydantic import Field

from app.mcp.core import READ, mcp
from app.mcp.db import session_scope
from app.mcp.schemas import CalendarOut, event_out
from app.services import calendar as calendar_service
from app.services.clock import local_today


@mcp.tool(title="Calendar", annotations=READ)
def get_calendar(
    days: Annotated[int, Field(ge=1, le=60, description="Number of days from start")] = 7,
    start: Annotated[date | None, Field(description="First day, default today")] = None,
) -> CalendarOut:
    """Calendar events (lectures, appointments) from the user's subscribed calendars.
    Deadlines from learning platforms are not events but tasks, see get_deadlines."""
    first = start or local_today()
    with session_scope() as session:
        found = calendar_service.events_between(session, first, first + timedelta(days=days))
        return CalendarOut(
            start=first,
            end=first + timedelta(days=days - 1),
            events=[event_out(e) for e in found],
        )
