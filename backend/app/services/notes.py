"""Notes: create, edit, append, archive and search.

Search uses the generated tsvector column (German stemming plus plain words) and falls back to
a substring match, so partial words ("postg") and names find something too. There is no delete;
archiving hides a note from the default list.
"""

import re
from dataclasses import dataclass

from sqlalchemy import any_, func, or_, select
from sqlalchemy.orm import Session

from app.models.notes import Note
from app.models.tasks import Area, Task
from app.schemas.notes import NoteCreate, NoteUpdate
from app.services import embeddings
from app.services.clock import utc_now
from app.services.tasks import area_lookup, find_area

CONTEXT_TAGS = ("context", "kontext")
SNIPPET_CHARS = 220
QUICK_TITLE_CHARS = 120
# Prefix in the quick-add line that makes a note instead of a task.
NOTE_PREFIX = re.compile(r"^\s*(?:notiz|note)\s*:\s*", re.IGNORECASE)
HASHTAG = re.compile(r"(?<!\S)#([\w-]+)")


class NoteError(ValueError):
    pass


def get_note(session: Session, note_id: int) -> Note:
    note = session.get(Note, note_id)
    if note is None:
        raise NoteError(f"No note with id {note_id}.")
    return note


def _check_refs(session: Session, area_id: int | None, task_id: int | None) -> None:
    if area_id is not None and session.get(Area, area_id) is None:
        raise NoteError(f"No area with id {area_id}.")
    if task_id is not None and session.get(Task, task_id) is None:
        raise NoteError(f"No task with id {task_id}.")


def create_note(session: Session, data: NoteCreate, source: str | None = None) -> Note:
    _check_refs(session, data.area_id, data.task_id)
    note = Note(
        title=" ".join(data.title.split()),
        body=data.body.replace("\r\n", "\n").strip(),
        area_id=data.area_id,
        tags=data.tags,
        pinned=data.pinned,
        task_id=data.task_id,
        source=source or data.source,
    )
    session.add(note)
    embeddings.embed_note(note)
    session.flush()
    session.refresh(note)
    return note


def update_note(session: Session, note: Note, data: NoteUpdate) -> Note:
    changes = data.model_dump(exclude_unset=True)
    _check_refs(session, changes.get("area_id"), changes.get("task_id"))
    if "archived" in changes:
        archived = changes.pop("archived")
        if archived and note.archived_at is None:
            note.archived_at = utc_now()
        elif archived is False:
            note.archived_at = None
    for key, value in changes.items():
        if key == "title" and value is not None:
            value = " ".join(value.split())
        if key == "body" and value is not None:
            value = value.replace("\r\n", "\n").strip()
        if key in ("title", "body", "tags", "pinned") and value is None:
            continue  # not clearable
        setattr(note, key, value)
    if "title" in changes or "body" in changes:
        embeddings.embed_note(note)
    session.flush()
    session.refresh(note)
    return note


def append(session: Session, note: Note, text: str) -> Note:
    """Add a paragraph at the end. Nothing already in the note changes."""
    text = text.replace("\r\n", "\n").strip()
    if not text:
        raise NoteError("Nothing to append.")
    note.body = f"{note.body.rstrip()}\n\n{text}" if note.body.strip() else text
    embeddings.embed_note(note)
    session.flush()
    session.refresh(note)
    return note


def quick_note(session: Session, text: str, source: str = "manual") -> Note:
    """A note from the quick-add field, e.g. "notiz: Idee für Compass #projekte #ideen".
    #words become the area (the first one that matches) or tags. The first line is the title,
    further lines the body; a first line too long for a title is kept whole in the body."""
    areas = area_lookup(session)
    area_slug: str | None = None
    tags: list[str] = []

    def hashtag(m: re.Match) -> str:
        nonlocal area_slug
        word = m.group(1).lower()
        if area_slug is None and word in areas:
            area_slug = areas[word]
        elif word not in tags:
            tags.append(word)
        return ""

    cleaned = HASHTAG.sub(hashtag, NOTE_PREFIX.sub("", text, count=1)).strip()
    lines = cleaned.splitlines()
    if not cleaned:
        raise NoteError("The note is empty.")
    title = " ".join(lines[0].split())
    body = "\n".join(line.rstrip() for line in lines[1:]).strip()
    if len(title) > QUICK_TITLE_CHARS:
        body = f"{title}\n\n{body}".strip()
        title = title[: QUICK_TITLE_CHARS - 1].rsplit(" ", 1)[0] + "…"
    area = find_area(session, area_slug) if area_slug else None
    return create_note(
        session,
        NoteCreate(title=title, body=body, area_id=area.id if area else None, tags=tags),
        source=source,
    )


# --- Reading -----------------------------------------------------------------------------------


@dataclass
class Found:
    note: Note
    snippet: str


def snippet(body: str, query: str | None = None) -> str:
    """The start of the body, or the part around the first word of the query found in it."""
    flat = " ".join(re.sub(r"[#*`>\[\]]", " ", body).split())
    start = 0
    for word in (query or "").lower().split():
        word = word.strip("\"'-")
        if len(word) >= 3 and (at := flat.lower().find(word[:6])) >= 0:
            start = max(0, at - 60)
            break
    part = flat[start : start + SNIPPET_CHARS]
    if start + SNIPPET_CHARS < len(flat):
        part = part.rsplit(" ", 1)[0] + " …"
    return ("… " if start else "") + part


def _like(query: str) -> str:
    return "%" + query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


def search(
    session: Session,
    query: str | None = None,
    area_id: int | None = None,
    tag: str | None = None,
    archived: bool = False,
    task_id: int | None = None,
    limit: int = 100,
) -> list[Found]:
    """Pinned notes first, then by relevance (with a query) or by last change."""
    stmt = select(Note).where(
        Note.archived_at.is_not(None) if archived else Note.archived_at.is_(None)
    )
    if area_id is not None:
        stmt = stmt.where(Note.area_id == area_id)
    if tag:
        stmt = stmt.where(any_(Note.tags) == tag.lower().lstrip("#"))
    if task_id is not None:
        stmt = stmt.where(Note.task_id == task_id)
    base = stmt
    query = (query or "").strip()
    order = [Note.pinned.desc()]
    if query:
        queries = [func.websearch_to_tsquery(c, query) for c in ("german", "english", "simple")]
        stmt = stmt.where(
            or_(
                *(Note.search.op("@@")(q) for q in queries),
                Note.title.ilike(_like(query), escape="\\"),
                Note.body.ilike(_like(query), escape="\\"),
            )
        )
        order.append(sum(func.ts_rank(Note.search, q) for q in queries).desc())
    order.append(Note.updated_at.desc())
    found = list(session.scalars(stmt.order_by(*order).limit(limit)).unique())
    if query and len(found) < limit and embeddings.configured():
        vec = embeddings.embed_query(query)
        if vec is not None:
            # The same filters, minus the words: notes that mean the same with other words.
            sem = embeddings.nearest(
                base.where(Note.id.notin_([n.id for n in found])), Note.embedding, vec
            )
            found += session.scalars(sem.limit(limit - len(found))).unique()
    return [Found(note=n, snippet=snippet(n.body, query)) for n in found]


def context_notes(session: Session) -> list[Note]:
    """Notes about the user (tag "context" or "kontext"), pinned first."""
    return list(
        session.scalars(
            select(Note)
            .where(
                Note.archived_at.is_(None),
                or_(*(any_(Note.tags) == tag for tag in CONTEXT_TAGS)),
            )
            .order_by(Note.pinned.desc(), Note.title)
        ).unique()
    )


def tag_counts(session: Session) -> list[tuple[str, int]]:
    tag = func.unnest(Note.tags).label("tag")
    rows = session.execute(
        select(tag, func.count())
        .where(Note.archived_at.is_(None))
        .group_by("tag")
        .order_by(func.count().desc(), "tag")
    )
    return [(t, n) for t, n in rows]
