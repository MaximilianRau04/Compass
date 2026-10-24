"""Sleep consistency, the resting heart rate trend and zone 2 minutes.

- Bed and wake times: median and standard deviation. Bed times are counted from noon, so 23:30
  and 00:30 are an hour apart and not 23 hours.
- Short nights: asleep under SHORT_NIGHT minutes. Early nights: the night before a day whose first
  timed calendar event starts before EARLY_EVENT.
- Resting heart rate: a 7-day mean per day and a warning when the latest 7-day mean is at least
  RESTING_ALERT bpm above the median of the period (often illness, stress or too little recovery).
- Zone 2: 60 to 70 % of the maximum heart rate (goal hr_max, default 178). Each heart rate sample
  counts until the next one, at most MAX_SAMPLE_GAP, so a watch taken off does not count.
"""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from statistics import median, pstdev

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.calendar import CalendarEvent
from app.models.health import DailyMetrics, HealthRecord, HeartRateSample, SleepSession
from app.models.training import TrainingSession
from app.services import nutrition
from app.services.clock import local_today, local_tz
from app.services.health import _record_window, _session_window, main_nights

SHORT_NIGHT = 7 * 60
EARLY_EVENT = time(10, 0)
RESTING_ALERT = 5
DEFAULT_HR_MAX = 178
ZONE2 = (0.60, 0.70)
MAX_SAMPLE_GAP = timedelta(minutes=5)


def _clock(minutes: float) -> str:
    m = round(minutes) % (24 * 60)
    return f"{m // 60:02d}:{m % 60:02d}"


@dataclass
class EarlyNight:
    date: date  # day of waking up
    first_event: str  # HH:MM
    title: str
    asleep_minutes: int


@dataclass
class SleepConsistency:
    nights: int
    median_bedtime: str | None
    median_wake_time: str | None
    bedtime_sd_minutes: int | None
    wake_time_sd_minutes: int | None
    short_nights: list[date]
    early_nights: list[EarlyNight]
    avg_asleep_early: int | None
    avg_asleep_other: int | None


def sleep_consistency(
    session: Session, days: int = 30, today: date | None = None
) -> SleepConsistency:
    today = today or local_today()
    since = today - timedelta(days=days - 1)
    tz = local_tz()
    nights = main_nights(
        list(
            session.scalars(
                select(SleepSession).where(
                    SleepSession.local_date >= since, SleepSession.local_date <= today
                )
            )
        )
    )
    bed = []
    wake = []
    for n in nights:
        start, end = n.start_at.astimezone(tz), n.end_at.astimezone(tz)
        bed.append(((start.hour * 60 + start.minute) - 12 * 60) % (24 * 60))
        wake.append(end.hour * 60 + end.minute)

    # First timed event per day, for the nights before early appointments.
    first: dict[date, CalendarEvent] = {}
    start_at = datetime.combine(since, time.min, tzinfo=tz)
    end_at = datetime.combine(today + timedelta(days=1), time.min, tzinfo=tz)
    for e in session.scalars(
        select(CalendarEvent)
        .where(
            CalendarEvent.all_day.is_(False),
            CalendarEvent.starts_at >= start_at,
            CalendarEvent.starts_at < end_at,
        )
        .order_by(CalendarEvent.starts_at)
    ):
        first.setdefault(e.starts_at.astimezone(tz).date(), e)
    early = []
    for n in nights:
        e = first.get(n.local_date)
        if e is not None and e.starts_at.astimezone(tz).time() < EARLY_EVENT:
            early.append(
                EarlyNight(
                    n.local_date,
                    e.starts_at.astimezone(tz).strftime("%H:%M"),
                    e.title,
                    n.asleep_minutes,
                )
            )
    early_dates = {x.date for x in early}
    other = [n.asleep_minutes for n in nights if n.local_date not in early_dates]

    return SleepConsistency(
        nights=len(nights),
        median_bedtime=_clock(median(bed) + 12 * 60) if bed else None,
        median_wake_time=_clock(median(wake)) if wake else None,
        bedtime_sd_minutes=round(pstdev(bed)) if len(bed) > 1 else None,
        wake_time_sd_minutes=round(pstdev(wake)) if len(wake) > 1 else None,
        short_nights=[n.local_date for n in nights if n.asleep_minutes < SHORT_NIGHT],
        early_nights=early,
        avg_asleep_early=round(sum(x.asleep_minutes for x in early) / len(early))
        if early
        else None,
        avg_asleep_other=round(sum(other) / len(other)) if other else None,
    )


@dataclass
class RestingDay:
    date: date
    bpm: int | None
    mean7: float | None


@dataclass
class RestingTrend:
    days: list[RestingDay]
    median: float | None
    latest_mean7: float | None
    alert: bool  # latest 7-day mean at least RESTING_ALERT above the median


def resting_trend(session: Session, days: int = 30, today: date | None = None) -> RestingTrend:
    today = today or local_today()
    since = today - timedelta(days=days - 1)
    values = {
        m.local_date: m.resting_hr
        for m in session.scalars(
            select(DailyMetrics).where(
                DailyMetrics.local_date >= since - timedelta(days=6),
                DailyMetrics.local_date <= today,
                DailyMetrics.resting_hr.is_not(None),
            )
        )
    }
    out = []
    for i in range(days):
        d = since + timedelta(days=i)
        window = [v for k, v in values.items() if d - timedelta(days=6) <= k <= d]
        out.append(
            RestingDay(d, values.get(d), round(sum(window) / len(window), 1) if window else None)
        )
    in_range = [v for k, v in values.items() if k >= since]
    mid = float(median(in_range)) if in_range else None
    latest = next((x.mean7 for x in reversed(out) if x.mean7 is not None), None)
    return RestingTrend(
        days=out,
        median=mid,
        latest_mean7=latest,
        alert=mid is not None and latest is not None and latest >= mid + RESTING_ALERT,
    )


# --- Zone 2 ------------------------------------------------------------------------------------


def hr_max(session: Session, day: date | None = None) -> int:
    return round(nutrition.goals_on(session, day or local_today()).get("hr_max", DEFAULT_HR_MAX))


def zone2_bounds(maximum: int) -> tuple[int, int]:
    return round(maximum * ZONE2[0]), round(maximum * ZONE2[1])


def _samples(session: Session, start: datetime, end: datetime) -> list[tuple[datetime, int]]:
    return list(
        session.execute(
            select(HeartRateSample.time, HeartRateSample.bpm)
            .join(HealthRecord, HealthRecord.id == HeartRateSample.record_id)
            .where(
                HeartRateSample.time >= start,
                HeartRateSample.time < end,
                HealthRecord.deleted_at.is_(None),
            )
            .order_by(HeartRateSample.time)
        )
    )


def zone2_minutes_in(
    samples: list[tuple[datetime, int]], low: int, high: int, end: datetime
) -> int:
    seconds = 0.0
    for i, (at, bpm) in enumerate(samples):
        until = samples[i + 1][0] if i + 1 < len(samples) else end
        if low <= bpm <= high:
            seconds += min(until - at, MAX_SAMPLE_GAP).total_seconds()
    return round(seconds / 60)


def session_window(session: Session, t: TrainingSession) -> tuple[datetime, datetime]:
    """The watch's recording of the session if there is one, else start plus duration."""
    record = session.get(HealthRecord, t.watch_record_id) if t.watch_record_id else None
    return _record_window(record) if record else _session_window(t)


def session_zone2(session: Session, t: TrainingSession, maximum: int | None = None) -> int:
    low, high = zone2_bounds(maximum or hr_max(session))
    start, end = session_window(session, t)
    return zone2_minutes_in(_samples(session, start, end), low, high, end)


@dataclass
class Zone2Week:
    week_start: date
    minutes: int  # all day long
    in_training: int  # within training sessions


def zone2_weeks(session: Session, weeks: int = 8, today: date | None = None) -> list[Zone2Week]:
    today = today or local_today()
    tz = local_tz()
    low, high = zone2_bounds(hr_max(session, today))
    first = today - timedelta(days=today.weekday()) - timedelta(weeks=weeks - 1)
    start = datetime.combine(first, time.min, tzinfo=tz)
    end = datetime.combine(today + timedelta(days=1), time.min, tzinfo=tz)
    samples = _samples(session, start, end)
    sessions = list(
        session.scalars(
            select(TrainingSession).where(
                TrainingSession.started_at >= start, TrainingSession.started_at < end
            )
        )
    )
    # Minutes per session, each counted within its own window.
    per_session = []
    for t in sessions:
        a, b = session_window(session, t)
        inside = [x for x in samples if a <= x[0] < b]
        per_session.append((a, zone2_minutes_in(inside, low, high, b)))

    out = []
    for i in range(weeks):
        ws = datetime.combine(first + timedelta(weeks=i), time.min, tzinfo=tz)
        we = ws + timedelta(weeks=1)
        week = [x for x in samples if ws <= x[0] < we]
        out.append(
            Zone2Week(
                week_start=ws.date(),
                minutes=zone2_minutes_in(week, low, high, min(we, end)),
                in_training=sum(m for a, m in per_session if ws <= a < we),
            )
        )
    return out


# --- Bedtime -----------------------------------------------------------------------------------

SLEEP_NEED = timedelta(hours=7, minutes=30)
FALL_ASLEEP = timedelta(minutes=30)


@dataclass
class Bedtime:
    day: date  # the day the event is on
    first_event_at: datetime
    title: str
    latest_bedtime: datetime  # first event minus SLEEP_NEED minus FALL_ASLEEP


def bedtime_for(session: Session, day: date) -> Bedtime | None:
    """The latest bedtime before a day: its first timed event minus 7.5 h of sleep and 30 min to
    fall asleep. None when the day has no timed event."""
    tz = local_tz()
    start = datetime.combine(day, time.min, tzinfo=tz)
    event = session.scalar(
        select(CalendarEvent)
        .where(
            CalendarEvent.all_day.is_(False),
            CalendarEvent.starts_at >= start,
            CalendarEvent.starts_at < start + timedelta(days=1),
        )
        .order_by(CalendarEvent.starts_at)
        .limit(1)
    )
    if event is None:
        return None
    first = event.starts_at.astimezone(tz)
    return Bedtime(day, first, event.title, first - SLEEP_NEED - FALL_ASLEEP)
