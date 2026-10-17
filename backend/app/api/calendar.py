from contextlib import nullcontext
from datetime import date, timedelta

from fastapi import APIRouter, HTTPException, status

from app.api.deps import SessionDep
from app.ingestion import calendar as calendar_sync
from app.schemas.calendar import CalendarEventRead, IntegrationStateRead
from app.services import integrations
from app.services.calendar import events_between

router = APIRouter(tags=["calendar"])

MAX_RANGE_DAYS = 92


@router.get("/calendar", response_model=list[CalendarEventRead])
def list_events(session: SessionDep, start: date, end: date):
    """Events overlapping the local days start..end (both inclusive)."""
    if end < start:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "end is before start")
    if (end - start).days >= MAX_RANGE_DAYS:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, f"range is limited to {MAX_RANGE_DAYS} days"
        )
    return events_between(session, start, end + timedelta(days=1))


@router.post("/calendar/sync")
def sync_calendars(session: SessionDep) -> dict[str, dict | str]:
    """Fetch all configured feeds now instead of waiting for the worker."""
    return calendar_sync.sync_all(lambda: nullcontext(session))


@router.get("/integrations", response_model=list[IntegrationStateRead])
def list_integrations(session: SessionDep):
    return integrations.list_states(session)
