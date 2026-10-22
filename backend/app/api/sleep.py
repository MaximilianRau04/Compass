from datetime import date
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status

from app.api.deps import SessionDep
from app.models.health import DailyMetrics, SleepSession
from app.models.integrations import IntegrationState
from app.schemas.health import (
    DailyMetricsRead,
    DayHeartRateRead,
    ExtraDayRead,
    HealthAverages,
    HealthSummaryRead,
    HeartRatePoint,
    SleepNightDetail,
    SleepNightRead,
    SleepStageRead,
    SyncStatus,
    WorkoutRead,
)
from app.services import health
from app.services.clock import local_today

router = APIRouter(prefix="/sleep", tags=["sleep"])


def night(s: SleepSession) -> SleepNightRead:
    return SleepNightRead(
        id=s.id,
        local_date=s.local_date,
        start_at=s.start_at,
        end_at=s.end_at,
        in_bed_minutes=s.in_bed_minutes,
        asleep_minutes=s.asleep_minutes,
        deep_minutes=s.deep_minutes,
        light_minutes=s.light_minutes,
        rem_minutes=s.rem_minutes,
        awake_minutes=s.awake_minutes,
        source_app=s.source_app,
    )


def night_detail(session, s: SleepSession) -> SleepNightDetail:
    return SleepNightDetail(
        **night(s).model_dump(),
        stages=[SleepStageRead(**x) for x in s.stages],
        heart_rate=[HeartRatePoint(time=t, bpm=b) for t, b in health.night_heart_rate(session, s)],
    )


def day(m: DailyMetrics) -> DailyMetricsRead:
    return DailyMetricsRead(
        date=m.local_date,
        steps=m.steps,
        kcal_burned=m.kcal_burned,
        resting_hr=m.resting_hr,
        hr_min=m.hr_min,
        hr_avg=m.hr_avg,
        hr_max=m.hr_max,
        sleep_minutes=m.sleep_minutes,
    )


@router.get("/summary", response_model=HealthSummaryRead)
def summary(session: SessionDep, days: Annotated[int, Query(ge=1, le=366)] = 30):
    s = health.summary(session, days)
    state = session.get(IntegrationState, "healthconnect")
    return HealthSummaryRead(
        since=s.since,
        until=s.until,
        last_night=night_detail(session, s.last_night) if s.last_night else None,
        nights=[night(n) for n in s.nights],
        days=[day(m) for m in s.days],
        averages=HealthAverages(**s.averages.__dict__),
        workouts=[
            WorkoutRead(
                id=w.record.id,
                source_app=w.record.source_app,
                start_at=w.record.start_at,
                end_at=w.record.end_at,
                duration_minutes=w.duration_minutes,
                title=w.title,
                exercise=w.exercise,
                gymday_duplicate=w.gymday_duplicate,
            )
            for w in s.workouts
        ],
        extras=[
            ExtraDayRead(date=d, **values)
            for d, values in sorted(health.extras(session, s.since, s.until).items())
        ],
        sync=SyncStatus(
            last_run_at=state.last_run_at,
            last_success_at=state.last_success_at,
            last_error=state.last_error,
            device=(state.stats or {}).get("device"),
        )
        if state
        else None,
    )


@router.get("/nights/{night_id}", response_model=SleepNightDetail)
def get_night(night_id: int, session: SessionDep):
    s = session.get(SleepSession, night_id)
    if s is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "night not found")
    return night_detail(session, s)


@router.get("/heart-rate", response_model=DayHeartRateRead)
def heart_rate(session: SessionDep, day: date | None = None):
    """The heart rate curve of one local day (default today) with its range and the night."""
    h = health.day_heart_rate(session, day or local_today())
    return DayHeartRateRead(
        date=h.day,
        points=[HeartRatePoint(time=t, bpm=b) for t, b in h.points],
        min=h.min,
        max=h.max,
        avg=h.avg,
        resting=h.resting,
        last=HeartRatePoint(time=h.last[0], bpm=h.last[1]) if h.last else None,
        sleep_start=h.sleep.start_at if h.sleep else None,
        sleep_end=h.sleep.end_at if h.sleep else None,
    )
