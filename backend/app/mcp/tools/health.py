"""Tools for sleep and the daily health data."""

from typing import Annotated

from mcp.server.mcpserver.exceptions import ToolError
from pydantic import AwareDatetime, Field

from app.config import get_settings
from app.mcp.core import READ, WRITE, mcp
from app.mcp.db import session_scope
from app.mcp.guards import audited
from app.mcp.schemas import (
    DailyDataOut,
    DayOut,
    DayRowOut,
    NightOut,
    SleepSummaryOut,
    WorkoutOut,
    consistency_out,
    resting_out,
)
from app.models.integrations import IntegrationState
from app.services import analysis, daily, health, sleep_log
from app.services.clock import local_tz


@mcp.tool(title="Sleep and health", annotations=READ)
def sleep_summary(
    days: Annotated[int, Field(ge=1, le=90, description="How many days back")] = 7,
) -> SleepSummaryOut:
    """Sleep per night (duration, bed and wake time, deep/light/REM/awake minutes), sleep
    consistency (median and spread of bed and wake time, nights under 7 h, nights before early
    events), the resting heart rate trend with an alert, and daily health metrics (steps, resting
    heart rate, calories burned) from the watch via Health Connect. A night belongs to the day of
    waking up."""
    tz = local_tz()
    with session_scope() as session:
        s = health.summary(session, days)
        state = session.get(IntegrationState, "healthconnect")
        return SleepSummaryOut(
            since=s.since,
            until=s.until,
            avg_sleep_minutes=s.averages.sleep_minutes,
            avg_resting_hr=s.averages.resting_hr,
            avg_steps=s.averages.steps,
            nights=[
                NightOut(
                    date=n.local_date,
                    bedtime=n.start_at.astimezone(tz).strftime("%H:%M"),
                    wake_time=n.end_at.astimezone(tz).strftime("%H:%M"),
                    asleep_minutes=n.asleep_minutes,
                    in_bed_minutes=n.in_bed_minutes,
                    deep_minutes=n.deep_minutes,
                    light_minutes=n.light_minutes,
                    rem_minutes=n.rem_minutes,
                    awake_minutes=n.awake_minutes,
                )
                for n in s.nights
            ],
            days=[
                DayOut(
                    date=m.local_date,
                    steps=m.steps,
                    resting_hr=m.resting_hr,
                    hr_min=m.hr_min,
                    hr_avg=m.hr_avg,
                    hr_max=m.hr_max,
                    kcal_burned=m.kcal_burned,
                    sleep_minutes=m.sleep_minutes,
                )
                for m in s.days
            ],
            other_workouts=[
                WorkoutOut(
                    date=w.record.local_date,
                    app=w.record.source_app,
                    exercise=w.exercise,
                    title=w.title,
                    duration_minutes=w.duration_minutes,
                    gymday_duplicate=w.gymday_duplicate,
                )
                for w in s.workouts
            ],
            last_sync=state.last_success_at if state else None,
            consistency=consistency_out(analysis.sleep_consistency(session, max(days, 14))),
            resting_hr=resting_out(analysis.resting_trend(session, max(days, 14))),
        )


@mcp.tool(title="Daily data", annotations=READ)
def daily_data(
    days: Annotated[
        int, Field(ge=7, le=180, description="How many days back, today included")
    ] = 30,
) -> DailyDataOut:
    """One row per day across all areas: the night that ended that morning (duration, bed and
    wake time, stages), steps, resting heart rate, training (sessions, sets, volume, zone 2
    minutes), logged calories and protein, the morning weight, the first appointment and the
    number of tasks completed. Use it to find relations between areas yourself, e.g. sleep after
    training days, resting heart rate after short nights, protein against strength, or sleep
    before early appointments. Missing values are missing data, not zero; today is still
    running."""
    with session_scope() as session:
        rows = daily.daily_rows(session, days)
        return DailyDataOut(
            since=rows[0].date,
            until=rows[-1].date,
            sleep_need_minutes=get_settings().sleep_need_minutes,
            hr_max=analysis.hr_max(session),
            days=[DayRowOut(**r.__dict__) for r in rows],
        )


@mcp.tool(title="Log sleep", annotations=WRITE)
def log_sleep(
    start_at: Annotated[
        AwareDatetime, Field(description="ISO timestamp with timezone: fell asleep")
    ],
    end_at: Annotated[AwareDatetime, Field(description="ISO timestamp with timezone: woke up")],
    awake_minutes: Annotated[
        int, Field(ge=0, le=600, description="Minutes spent lying awake during the night")
    ] = 0,
) -> NightOut:
    """Record a night of sleep by hand, e.g. when the watch was not worn. Fails on overlapping
    manual nights or future wake times."""
    args = {"start_at": start_at, "end_at": end_at, "awake_minutes": awake_minutes}
    tz = local_tz()
    with audited("log_sleep", args) as session:
        try:
            night = sleep_log.add(
                session,
                sleep_log.ManualNight(
                    start_at=start_at, end_at=end_at, awake_minutes=awake_minutes
                ),
            )
        except sleep_log.SleepLogError as exc:
            raise ToolError(str(exc)) from exc
        return NightOut(
            date=night.local_date,
            bedtime=night.start_at.astimezone(tz).strftime("%H:%M"),
            wake_time=night.end_at.astimezone(tz).strftime("%H:%M"),
            asleep_minutes=night.asleep_minutes,
            in_bed_minutes=night.in_bed_minutes,
            deep_minutes=night.deep_minutes,
            light_minutes=night.light_minutes,
            rem_minutes=night.rem_minutes,
            awake_minutes=night.awake_minutes,
        )
