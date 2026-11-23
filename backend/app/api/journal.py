from datetime import date, timedelta
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status

from app.api.deps import SessionDep
from app.schemas.journal import (
    JournalBrief,
    JournalDayRead,
    JournalNote,
    JournalRead,
    JournalWrite,
)
from app.services import journal
from app.services.clock import local_today

router = APIRouter(prefix="/journal", tags=["journal"])


@router.get("", response_model=list[JournalRead])
def list_entries(session: SessionDep, days: Annotated[int, Query(ge=1, le=366)] = 30):
    """Entries of the last `days` days, newest first."""
    today = local_today()
    return journal.entries(session, today - timedelta(days=days - 1), today)


@router.get("/{day}", response_model=JournalDayRead)
def get_day(day: date, session: SessionDep):
    """The entry of a day together with what the day held."""
    d = journal.day(session, day)
    r = d.row
    return JournalDayRead(
        date=d.date,
        entry=JournalRead.model_validate(d.entry) if d.entry else None,
        briefs=[JournalBrief(kind=k, title=t, body=b) for k, t, b in d.briefs],
        tasks_done=d.tasks_done,
        notes=[JournalNote(id=i, title=title) for i, title in d.notes],
        training=r.training,
        asleep_minutes=r.asleep_minutes,
        steps=r.steps,
        resting_hr=r.resting_hr,
        kcal=r.kcal,
        protein_g=r.protein_g,
        weight_kg=r.weight_kg,
    )


@router.put("/{day}", response_model=JournalRead | None)
def save_day(day: date, data: JournalWrite, session: SessionDep):
    """Fields left out keep their value, null clears mood or energy. A day left without mood,
    energy and text has no entry, the answer is then null."""
    fields = {name: getattr(data, name) for name in data.model_fields_set}
    try:
        entry = journal.save(session, day, **fields)
    except journal.JournalError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    session.commit()
    return entry
