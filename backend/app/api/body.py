from typing import Annotated

from fastapi import APIRouter, HTTPException, Query

from app.api.deps import SessionDep
from app.schemas.body import BodyLog, BodyTrendRead, DayWeightRead, WaistRead, WeekBodyRead
from app.services import body

router = APIRouter(prefix="/body", tags=["body"])


def trend_read(t: body.Trend) -> BodyTrendRead:
    return BodyTrendRead(
        today=t.today,
        days=[DayWeightRead(**d.__dict__) for d in t.days],
        mean7=t.mean7,
        mean7_before=t.mean7_before,
        change_kg=t.change_kg,
        change_pct=t.change_pct,
        loss_per_week=t.loss_per_week,
        loss_min=t.loss_min,
        loss_max=t.loss_max,
        status=t.status,
        waist=[WaistRead(**w.__dict__) for w in t.waist],
        waist_change=t.waist_change,
        weeks=[WeekBodyRead(week_start=ws, kg=kg, waist_cm=cm) for ws, kg, cm in t.weekly],
    )


@router.post("/log", response_model=BodyTrendRead)
def log(data: BodyLog, session: SessionDep):
    """Enter today's (or another day's) weight or waist; the same day again replaces it."""
    try:
        body.log(session, data.metric, data.value, data.day)
    except body.BodyError as exc:
        raise HTTPException(422, str(exc)) from exc
    session.commit()
    return trend_read(body.trend(session))


@router.get("/trend", response_model=BodyTrendRead)
def trend(session: SessionDep, weeks: Annotated[int, Query(ge=2, le=52)] = 8):
    return trend_read(body.trend(session, weeks))
