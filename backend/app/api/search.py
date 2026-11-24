from typing import Annotated

from fastapi import APIRouter, Query

from app.api import mail as mail_api
from app.api import notes as notes_api
from app.api.deps import SessionDep
from app.schemas.search import SearchRead
from app.services import search as search_service

router = APIRouter(tags=["search"])


@router.get("/search", response_model=SearchRead)
def search(
    session: SessionDep,
    q: Annotated[str, Query(max_length=200)],
    limit: Annotated[int, Query(ge=1, le=30)] = 8,
):
    """Tasks, notes, journal entries, calendar events and mails that contain the words of q.
    Shorter than two characters finds nothing."""
    found = search_service.search(session, q, limit)
    return {
        "tasks": found.tasks,
        "notes": [notes_api.list_item(f) for f in found.notes],
        "journal": [
            {
                "local_date": f.entry.local_date,
                "mood": f.entry.mood,
                "energy": f.entry.energy,
                "snippet": f.snippet,
            }
            for f in found.journal
        ],
        "events": found.events,
        "mails": [mail_api.read(e) for e in found.mails],
    }
