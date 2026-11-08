"""Tools for the notes knowledge base."""

from typing import Annotated

from mcp.server.mcpserver.exceptions import ToolError
from pydantic import Field

from app.mcp.core import READ, WRITE, mcp
from app.mcp.db import session_scope
from app.mcp.guards import area_id_for, audited
from app.mcp.schemas import ContextOut, NoteOut, NotesOut, NoteSummaryOut, note_out
from app.schemas.notes import NoteCreate
from app.services import notes as note_service
from app.services.clock import local_tz
from app.services.notes import NoteError


@mcp.tool(title="Search notes", annotations=READ)
def search_notes(
    query: Annotated[
        str | None, Field(max_length=200, description="Words to find; empty lists the newest")
    ] = None,
    area: Annotated[str | None, Field(description="Area slug, see list_areas")] = None,
    tag: str | None = None,
    limit: Annotated[int, Field(ge=1, le=50)] = 10,
) -> NotesOut:
    """Search the user's notes (title and text, German stemming, partial words). Pinned notes
    come first. Use get_note for the full text."""
    with session_scope() as session:
        found = note_service.search(session, query, area_id_for(session, area), tag, limit=limit)
        tz = local_tz()
        return NotesOut(
            count=len(found),
            notes=[
                NoteSummaryOut(
                    id=f.note.id,
                    title=f.note.title,
                    area=f.note.area.slug if f.note.area else None,
                    tags=list(f.note.tags),
                    pinned=f.note.pinned,
                    updated=f.note.updated_at.astimezone(tz).strftime("%Y-%m-%d %H:%M"),
                    snippet=f.snippet,
                )
                for f in found
            ],
        )


@mcp.tool(title="Get note", annotations=READ)
def get_note(note_id: int) -> NoteOut:
    """Get one note with its full Markdown text."""
    with session_scope() as session:
        try:
            return note_out(note_service.get_note(session, note_id))
        except NoteError as exc:
            raise ToolError(f"{exc} Use search_notes to find the right id.") from exc


@mcp.tool(title="User context", annotations=READ)
def get_context() -> ContextOut:
    """Notes about the user: who they are, their projects and offers, target groups, branding
    and writing style (notes tagged "context" or "kontext"). Read them before writing in the
    user's name."""
    with session_scope() as session:
        notes = note_service.context_notes(session)
        return ContextOut(
            note="Written by the user about themselves. Follow the writing style it describes."
            if notes
            else 'No context notes yet. The user can tag notes with "context" in Compass.',
            notes=[note_out(n) for n in notes],
        )


@mcp.tool(title="Add note", annotations=WRITE)
def add_note(
    title: Annotated[str, Field(min_length=1, max_length=300)],
    body: Annotated[
        str, Field(max_length=100_000, description="Markdown: ## headings, - lists, links")
    ] = "",
    area: Annotated[str | None, Field(description="Area slug, see list_areas")] = None,
    tags: Annotated[
        list[str] | None, Field(description='e.g. ["ideas"]; "context" = about the user')
    ] = None,
    task_id: Annotated[int | None, Field(description="Task the note belongs to")] = None,
    pinned: Annotated[bool, Field(description="Keep it at the top of the list")] = False,
) -> NoteOut:
    """Create a note. Search first (search_notes) and prefer append_note when a note on the
    topic exists."""
    with audited("add_note", {"title": title, "area": area, "task_id": task_id}) as session:
        note = note_service.create_note(
            session,
            NoteCreate(
                title=title,
                body=body,
                area_id=area_id_for(session, area),
                tags=tags or [],
                task_id=task_id,
                pinned=pinned,
            ),
            source="claude",
        )
        return note_out(note)


@mcp.tool(title="Append to note", annotations=WRITE)
def append_note(
    note_id: int,
    text: Annotated[str, Field(min_length=1, max_length=20_000, description="Markdown")],
) -> NoteOut:
    """Add a paragraph at the end of a note. Nothing already in it changes."""
    with audited("append_note", {"note_id": note_id, "chars": len(text)}) as session:
        note = note_service.append(session, note_service.get_note(session, note_id), text)
        return note_out(note)
