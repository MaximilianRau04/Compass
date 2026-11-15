"""Tools for the journal: mood, energy and a text per day."""

from datetime import date, timedelta
from typing import Annotated

from mcp.server.mcpserver.exceptions import ToolError
from pydantic import BaseModel, Field

from app.mcp.core import READ, WRITE, mcp
from app.mcp.db import session_scope
from app.mcp.guards import audited
from app.services import journal
from app.services.clock import local_today


class JournalEntryOut(BaseModel):
    date: date
    mood: int | None = Field(description="1 (bad) to 5 (great)")
    energy: int | None = Field(description="1 (drained) to 5 (full of energy)")
    text: str


class JournalOut(BaseModel):
    count: int
    entries: list[JournalEntryOut] = Field(description="Newest first")


def _out(e) -> JournalEntryOut:
    return JournalEntryOut(date=e.local_date, mood=e.mood, energy=e.energy, text=e.text)


@mcp.tool(title="Journal", annotations=READ)
def get_journal(
    days: Annotated[int, Field(ge=1, le=366, description="How many days back")] = 14,
) -> JournalOut:
    """The user's journal: per day mood and energy (1 to 5) and a free text. Days without an
    entry are missing. Combine it with daily_data to see what goes along with good or bad days."""
    with session_scope() as session:
        today = local_today()
        found = journal.entries(session, today - timedelta(days=days - 1), today)
        return JournalOut(count=len(found), entries=[_out(e) for e in found])


@mcp.tool(title="Write journal", annotations=WRITE)
def write_journal(
    text: Annotated[
        str | None, Field(max_length=journal.MAX_TEXT, description="Added as a new paragraph")
    ] = None,
    mood: Annotated[int | None, Field(ge=1, le=5)] = None,
    energy: Annotated[int | None, Field(ge=1, le=5)] = None,
    day: Annotated[date | None, Field(description="YYYY-MM-DD, default today")] = None,
) -> JournalEntryOut:
    """Record how the user's day went, as the user said: mood and energy only when the user
    rated them, the text in the user's words. The text is appended to the day's entry, never
    replacing what is there."""
    args = {"day": day, "mood": mood, "energy": energy, "text": text}
    # Only what the user said: a value left out keeps what is there.
    given = {k: v for k, v in args.items() if k != "day" and v is not None}
    if not given:
        raise ToolError("give a text, a mood or an energy")
    with audited("write_journal", args) as session:
        try:
            entry = journal.save(session, day, **given, append=True)
        except journal.JournalError as exc:
            raise ToolError(str(exc)) from exc
        if entry is None:
            raise ToolError("nothing to write: the text is empty")
        return _out(entry)
