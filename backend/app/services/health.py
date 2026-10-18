"""Sleep and health data from Health Connect, shared by the REST API, the MCP server and the
ingestion: daily metrics, the summary for the sleep tab and the Gym Day duration match."""

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from statistics import mean

from sqlalchemy import Integer, and_, func, or_, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.health import DailyMetrics, HealthRecord, HeartRateSample, SleepSession
from app.models.training import TrainingSession
from app.services.clock import local_today, local_tz, utc_now

# A Gym Day session from the CSV and its Health Connect entry are the same session when the CSV
# timestamp lies within the Health Connect session, give or take this much.
GYMDAY_SLACK = timedelta(hours=1)
# Source of a training session that only exists in Health Connect (no sets from the CSV).
HEALTHCONNECT_SESSION = "healthconnect"


def _day_bounds(first: date, last: date) -> tuple[datetime, datetime]:
    tz = local_tz()
    return (
        datetime.combine(first, time.min, tz),
        datetime.combine(last + timedelta(days=1), time.min, tz),
    )


def _best_source(totals: dict[str, float]) -> tuple[str, float] | None:
    """The source with the largest total, so two apps writing the same steps never add up."""
    return max(totals.items(), key=lambda item: item[1]) if totals else None


def _per_source(session: Session, kind: str, field: str, days: set[date]) -> dict:
    value = HealthRecord.raw["data"][field].as_float()
    rows = session.execute(
        select(HealthRecord.local_date, HealthRecord.source_app, func.sum(value))
        .where(
            HealthRecord.type == kind,
            HealthRecord.deleted_at.is_(None),
            HealthRecord.local_date.in_(days),
        )
        .group_by(HealthRecord.local_date, HealthRecord.source_app)
    )
    out: dict[date, dict[str, float]] = defaultdict(dict)
    for day, source, total in rows:
        if total is not None:
            out[day][source] = float(total)
    return out


def recompute_days(session: Session, days: set[date]) -> None:
    if not days:
        return
    steps = _per_source(session, "steps", "count", days)
    kcal = _per_source(session, "total_calories", "kcal", days)

    resting: dict[date, list[float]] = defaultdict(list)
    for day, bpm in session.execute(
        select(HealthRecord.local_date, HealthRecord.raw["data"]["bpm"].as_float()).where(
            HealthRecord.type == "resting_heart_rate",
            HealthRecord.deleted_at.is_(None),
            HealthRecord.local_date.in_(days),
        )
    ):
        if bpm is not None:
            resting[day].append(bpm)

    tz_name = get_settings().timezone
    sample_day = func.date(func.timezone(tz_name, HeartRateSample.time))
    start, end = _day_bounds(min(days), max(days))
    heart = {
        day: (low, avg, high)
        for day, low, avg, high in session.execute(
            select(
                sample_day,
                func.min(HeartRateSample.bpm),
                func.avg(HeartRateSample.bpm),
                func.max(HeartRateSample.bpm),
            )
            .join(HealthRecord, HealthRecord.id == HeartRateSample.record_id)
            .where(
                HeartRateSample.time >= start,
                HeartRateSample.time < end,
                HealthRecord.deleted_at.is_(None),
            )
            .group_by(sample_day)
        )
        if day in days
    }

    sleep: dict[date, dict[str, float]] = defaultdict(dict)
    for day, source, total in session.execute(
        select(
            SleepSession.local_date,
            SleepSession.source_app,
            func.sum(SleepSession.asleep_minutes),
        )
        .where(SleepSession.local_date.in_(days))
        .group_by(SleepSession.local_date, SleepSession.source_app)
    ):
        sleep[day][source] = float(total)

    existing = {
        m.local_date: m
        for m in session.scalars(select(DailyMetrics).where(DailyMetrics.local_date.in_(days)))
    }
    now = utc_now()
    for day in days:
        best_steps = _best_source(steps.get(day, {}))
        best_kcal = _best_source(kcal.get(day, {}))
        best_sleep = _best_source(sleep.get(day, {}))
        hr = heart.get(day)
        values = {
            "steps": round(best_steps[1]) if best_steps else None,
            "steps_source": best_steps[0] if best_steps else None,
            "kcal_burned": round(best_kcal[1]) if best_kcal else None,
            "resting_hr": round(mean(resting[day])) if resting.get(day) else None,
            "hr_min": hr[0] if hr else None,
            "hr_avg": round(float(hr[1])) if hr else None,
            "hr_max": hr[2] if hr else None,
            "sleep_minutes": round(best_sleep[1]) if best_sleep else None,
        }
        row = existing.get(day)
        if all(v is None for v in values.values()):
            if row is not None:
                session.delete(row)
            continue
        if row is None:
            row = DailyMetrics(local_date=day)
            session.add(row)
        for field, value in values.items():
            setattr(row, field, value)
        row.updated_at = now
    session.flush()


def match_gymday_sessions(session: Session, first: date, last: date) -> int:
    """Link Gym Day sessions from the CSV to their Health Connect entry and take its duration.

    The CSV has a timestamp but no duration; Gym Day writes every session (name, start and end,
    no sets) to Health Connect, also without a Premium export. Pairs are matched one to one,
    closest start first. A Health Connect session without a CSV session becomes a training
    session of its own without sets (source "healthconnect"); once a CSV import brings its sets,
    the CSV session takes over and the placeholder goes away. Returns the number of sessions
    with a Health Connect entry in the range."""
    apps = get_settings().gymday_apps
    start, end = _day_bounds(first - timedelta(days=1), last + timedelta(days=1))
    in_range = list(
        session.scalars(
            select(TrainingSession).where(
                TrainingSession.started_at >= start, TrainingSession.started_at < end
            )
        )
    )
    trainings = [t for t in in_range if t.source != HEALTHCONNECT_SESSION]
    records = list(
        session.scalars(
            select(HealthRecord).where(
                HealthRecord.type == "exercise",
                HealthRecord.deleted_at.is_(None),
                HealthRecord.source_app.in_(apps),
                HealthRecord.start_at >= start - GYMDAY_SLACK,
                HealthRecord.start_at < end + GYMDAY_SLACK,
            )
        )
    )
    # Placeholders in the range plus those of records in the slack just outside it.
    placeholders = {
        t.health_record_id: t
        for t in session.scalars(
            select(TrainingSession).where(
                TrainingSession.source == HEALTHCONNECT_SESSION,
                or_(
                    and_(TrainingSession.started_at >= start, TrainingSession.started_at < end),
                    TrainingSession.health_record_id.in_([r.id for r in records]),
                ),
            )
        )
    }
    pairs = sorted(
        (abs(r.start_at - t.started_at), t.id, r.id)
        for t in trainings
        for r in records
        if r.start_at - GYMDAY_SLACK <= t.started_at <= r.end_at + GYMDAY_SLACK
    )
    linked: dict[int, str] = {}
    used: set[str] = set()
    for _, training_id, record_id in pairs:
        if training_id in linked or record_id in used:
            continue
        linked[training_id] = record_id
        used.add(record_id)

    # Placeholders whose record is gone or now belongs to a CSV session go first, so the
    # record id is free (it is unique on training_sessions).
    by_id = {r.id: r for r in records}
    for record_id in list(placeholders):
        if record_id not in by_id or record_id in used:
            session.delete(placeholders.pop(record_id))
    for t in trainings:
        t.health_record_id = None
    session.flush()

    for t in trainings:
        record = by_id.get(linked.get(t.id, ""))
        t.health_record_id = record.id if record else None
        t.duration_minutes = _minutes_between(record) if record else None
    for record in records:
        if record.id in used:
            continue
        placeholder = placeholders.get(record.id)
        if placeholder is None:
            placeholder = TrainingSession(source=HEALTHCONNECT_SESSION, health_record_id=record.id)
            session.add(placeholder)
        title = ((record.raw.get("data") or {}).get("title") or "").strip()
        placeholder.started_at = record.start_at
        placeholder.workout_name = title[:120] or "Training"
        placeholder.duration_minutes = _minutes_between(record)
    session.flush()
    return len(records)


def _minutes_between(record: HealthRecord) -> int:
    return round((record.end_at - record.start_at).total_seconds() / 60)


# --- Reading -----------------------------------------------------------------------------------


@dataclass
class Workout:
    record: HealthRecord
    duration_minutes: int
    title: str | None
    exercise: str | None
    gymday_duplicate: bool


@dataclass
class Averages:
    sleep_minutes: int | None
    deep_minutes: int | None
    light_minutes: int | None
    rem_minutes: int | None
    awake_minutes: int | None
    resting_hr: int | None
    steps: int | None


@dataclass
class Summary:
    since: date
    until: date
    last_night: SleepSession | None
    nights: list[SleepSession]
    days: list[DailyMetrics]
    averages: Averages
    workouts: list[Workout]


def _avg(values: list[int | None]) -> int | None:
    present = [v for v in values if v is not None]
    return round(mean(present)) if present else None


def main_nights(sessions: list[SleepSession]) -> list[SleepSession]:
    """The longest session per wake-up day (naps and the second app's copy drop out)."""
    best: dict[date, SleepSession] = {}
    for s in sessions:
        if s.local_date not in best or s.asleep_minutes > best[s.local_date].asleep_minutes:
            best[s.local_date] = s
    return [best[d] for d in sorted(best)]


def workouts(session: Session, since: date, until: date) -> list[Workout]:
    """Exercise sessions from other apps than Gym Day (e.g. Zepp). A Zepp workout recorded during
    a Gym Day session is flagged as a duplicate instead of counting as a second training."""
    apps = get_settings().gymday_apps
    start, end = _day_bounds(since, until)
    records = list(
        session.scalars(
            select(HealthRecord)
            .where(
                HealthRecord.type == "exercise",
                HealthRecord.deleted_at.is_(None),
                HealthRecord.start_at >= start - timedelta(hours=6),
                HealthRecord.start_at < end,
            )
            .order_by(HealthRecord.start_at.desc())
        )
    )
    gym = [r for r in records if r.source_app in apps]
    gym_starts = list(
        session.scalars(
            select(TrainingSession.started_at).where(
                TrainingSession.started_at >= start - timedelta(hours=6),
                TrainingSession.started_at < end,
            )
        )
    )
    out = []
    for r in records:
        if r.source_app in apps or r.start_at < start:
            continue
        overlaps = any(g.start_at < r.end_at and r.start_at < g.end_at for g in gym) or any(
            r.start_at - GYMDAY_SLACK <= t <= r.end_at for t in gym_starts
        )
        data = r.raw.get("data") or {}
        out.append(
            Workout(
                record=r,
                duration_minutes=round((r.end_at - r.start_at).total_seconds() / 60),
                title=(data.get("title") or None),
                exercise=(data.get("exercise") or None),
                gymday_duplicate=overlaps,
            )
        )
    return out


def summary(session: Session, days: int) -> Summary:
    until = local_today()
    since = until - timedelta(days=days - 1)
    sessions = list(
        session.scalars(
            select(SleepSession)
            .where(SleepSession.local_date >= since, SleepSession.local_date <= until)
            .order_by(SleepSession.start_at)
        )
    )
    nights = main_nights(sessions)
    metrics = list(
        session.scalars(
            select(DailyMetrics)
            .where(DailyMetrics.local_date >= since, DailyMetrics.local_date <= until)
            .order_by(DailyMetrics.local_date)
        )
    )
    # The latest night, even if it is older than the range (e.g. the watch was not worn).
    last = session.scalar(
        select(SleepSession).order_by(
            SleepSession.local_date.desc(), SleepSession.asleep_minutes.desc()
        )
    )
    return Summary(
        since=since,
        until=until,
        last_night=last,
        nights=nights,
        days=metrics,
        averages=Averages(
            sleep_minutes=_avg([n.asleep_minutes for n in nights]),
            deep_minutes=_avg([n.deep_minutes for n in nights]),
            light_minutes=_avg([n.light_minutes for n in nights]),
            rem_minutes=_avg([n.rem_minutes for n in nights]),
            awake_minutes=_avg([n.awake_minutes for n in nights]),
            resting_hr=_avg([m.resting_hr for m in metrics]),
            steps=_avg([m.steps for m in metrics]),
        ),
        workouts=workouts(session, since, until),
    )


def night_heart_rate(session: Session, night: SleepSession, minutes: int = 5) -> list[tuple]:
    """Heart rate during a night as averages over `minutes` buckets."""
    bucket = func.to_timestamp(
        func.floor(func.extract("epoch", HeartRateSample.time) / (minutes * 60)) * (minutes * 60)
    )
    return list(
        session.execute(
            select(bucket.label("t"), func.avg(HeartRateSample.bpm).cast(Integer))
            .join(HealthRecord, HealthRecord.id == HeartRateSample.record_id)
            .where(
                HeartRateSample.time >= night.start_at,
                HeartRateSample.time <= night.end_at,
                HealthRecord.deleted_at.is_(None),
            )
            .group_by("t")
            .order_by("t")
        )
    )
