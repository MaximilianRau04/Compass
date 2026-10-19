from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status

from app.api.deps import SessionDep
from app.models.notes import Note
from app.schemas.notes import NoteCreate, NoteListItem, NoteRead, NoteUpdate, QuickNote, TagCount
from app.schemas.tasks import AreaRead
from app.services import notes as note_service
from app.services.notes import NoteError

router = APIRouter(prefix="/notes", tags=["notes"])


def read(note: Note) -> NoteRead:
    return NoteRead(
        id=note.id,
        title=note.title,
        body=note.body,
        area_id=note.area_id,
        area=AreaRead.model_validate(note.area) if note.area else None,
        tags=list(note.tags),
        pinned=note.pinned,
        archived=note.archived_at is not None,
        source=note.source,
        task_id=note.task_id,
        created_at=note.created_at,
        updated_at=note.updated_at,
    )


def _get(session, note_id: int) -> Note:
    try:
        return note_service.get_note(session, note_id)
    except NoteError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc


@router.get("", response_model=list[NoteListItem])
def list_notes(
    session: SessionDep,
    q: Annotated[str | None, Query(max_length=200)] = None,
    area_id: int | None = None,
    tag: str | None = None,
    archived: bool = False,
    task_id: int | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
):
    found = note_service.search(session, q, area_id, tag, archived, task_id, limit)
    return [
        NoteListItem(
            id=f.note.id,
            title=f.note.title,
            snippet=f.snippet,
            area=AreaRead.model_validate(f.note.area) if f.note.area else None,
            tags=list(f.note.tags),
            pinned=f.note.pinned,
            archived=f.note.archived_at is not None,
            source=f.note.source,
            task_id=f.note.task_id,
            updated_at=f.note.updated_at,
        )
        for f in found
    ]


@router.get("/tags", response_model=list[TagCount])
def tags(session: SessionDep):
    return [TagCount(tag=t, count=n) for t, n in note_service.tag_counts(session)]


@router.get("/{note_id}", response_model=NoteRead)
def get_note(note_id: int, session: SessionDep):
    return read(_get(session, note_id))


@router.post("", response_model=NoteRead, status_code=status.HTTP_201_CREATED)
def create_note(data: NoteCreate, session: SessionDep):
    try:
        note = note_service.create_note(session, data)
    except NoteError as exc:
        raise HTTPException(422, str(exc)) from exc
    session.commit()
    return read(note)


@router.post("/quick", response_model=NoteRead, status_code=status.HTTP_201_CREATED)
def quick_note(data: QuickNote, session: SessionDep):
    """A note from the quick-add line ("notiz: ... #area #tag")."""
    try:
        note = note_service.quick_note(session, data.text)
    except NoteError as exc:
        raise HTTPException(422, str(exc)) from exc
    session.commit()
    return read(note)


@router.patch("/{note_id}", response_model=NoteRead)
def update_note(note_id: int, data: NoteUpdate, session: SessionDep):
    note = _get(session, note_id)
    try:
        note_service.update_note(session, note, data)
    except NoteError as exc:
        raise HTTPException(422, str(exc)) from exc
    session.commit()
    return read(note)
