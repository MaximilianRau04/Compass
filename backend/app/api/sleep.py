from datetime import date, timedelta
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status

from app.api.deps import SessionDep
from app.config import get_settings
from app.models.health import DailyMetrics, SleepSession
from app.models.integrations import IntegrationState
from app.schemas.health import (
    DailyMetricsRead,
    DayHeartRateRead,
    EarlyNightRead,
    ExtraDayRead,
    HealthAnalysisRead,
    HealthAverages,
    HealthSummaryRead,
    HeartRatePoint,
    RestingDayRead,
    RestingTrendRead,
    SleepConsistencyRead,
    SleepNightDetail,
    SleepNightRead,
    SleepStageRead,
    SyncStatus,
    WorkoutRead,
    Zone2WeekRead,
)
from app.services import analysis, health
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


@router.get("/analysis", response_model=HealthAnalysisRead)
def health_analysis(
    session: SessionDep,
    days: Annotated[int, Query(ge=7, le=180)] = 30,
    weeks: Annotated[int, Query(ge=1, le=26)] = 8,
):
    """Sleep consistency, the resting heart rate trend and zone 2 minutes per week."""
    c = analysis.sleep_consistency(session, days)
    r = analysis.resting_trend(session, days)
    maximum = analysis.hr_max(session)
    low, high = analysis.zone2_bounds(maximum)
    return HealthAnalysisRead(
        consistency=SleepConsistencyRead(
            **{k: v for k, v in c.__dict__.items() if k != "early_nights"},
            early_nights=[EarlyNightRead(**x.__dict__) for x in c.early_nights],
        ),
        resting=RestingTrendRead(
            days=[RestingDayRead(**d.__dict__) for d in r.days],
            median=r.median,
            latest_mean7=r.latest_mean7,
            alert=r.alert,
        ),
        hr_max=maximum,
        zone2_low=low,
        zone2_high=high,
        zone2_weeks=[Zone2WeekRead(**w.__dict__) for w in analysis.zone2_weeks(session, weeks)],
    )


@router.get("/bedtime")
def bedtime(session: SessionDep, day: date | None = None) -> dict:
    """The latest bedtime before a day (default tomorrow), see analysis.bedtime_for. Empty when the
    day has no appointment."""
    b = analysis.bedtime_for(session, day or local_today() + timedelta(days=1))
    if b is None:
        return {"day": (day or local_today() + timedelta(days=1)).isoformat(), "event": None}
    return {
        "day": b.day.isoformat(),
        "event": {"title": b.title, "starts_at": b.first_event_at.isoformat()},
        "wake_at": b.wake_at.isoformat(),
        "latest_bedtime": b.latest_bedtime.isoformat(),
        "sleep_need_minutes": get_settings().sleep_need_minutes,
        "fall_asleep_minutes": get_settings().fall_asleep_minutes,
    }
