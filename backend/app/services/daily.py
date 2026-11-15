"""One row per day across sleep, health, training, nutrition, weight, calendar and tasks, so an
assistant can look for relations itself (sleep after leg days, resting heart rate after short
nights, protein against strength). Missing data stays None: a day without nutrition entries was
not logged, a day without a night was not worn."""

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.health import DailyMetrics, SleepSession
from app.models.journal import JournalEntry
from app.models.tasks import Task, TaskStatus
from app.models.training import TrainingSession
from app.services import analysis, health, nutrition, training
from app.services.clock import local_today, local_tz


@dataclass
class DayRow:
    date: date
    # The night that ended this morning.
    asleep_minutes: int | None = None
    bedtime: str | None = None  # HH:MM the night before
    wake_time: str | None = None
    deep_minutes: int | None = None
    rem_minutes: int | None = None
    awake_minutes: int | None = None
    steps: int | None = None
    resting_hr: int | None = None
    kcal_burned: int | None = None
    training: list[str] = field(default_factory=list)  # "Push (push, 62 min)"
    sets: int = 0
    volume_kg: float = 0.0
    zone2_minutes: int = 0
    kcal: int | None = None
    protein_g: int | None = None
    nutrition_flags: list[str] = field(default_factory=list)
    weight_kg: float | None = None
    first_event: str | None = None  # "08:00 Vorlesung"
    tasks_done: int = 0
    mood: int | None = None  # journal, 1 to 5
    energy: int | None = None


def _round(value: float | None) -> int | None:
    return round(value) if value is not None else None


def daily_rows(session: Session, days: int, today: date | None = None) -> list[DayRow]:
    """Oldest first, today included (today is still running)."""
    tz = local_tz()
    until = today or local_today()
    since = until - timedelta(days=days - 1)
    rows = {since + timedelta(days=i): DayRow(since + timedelta(days=i)) for i in range(days)}

    nights = health.main_nights(
        list(
            session.scalars(
                select(SleepSession).where(
                    SleepSession.local_date >= since, SleepSession.local_date <= until
                )
            )
        )
    )
    for n in nights:
        r = rows[n.local_date]
        r.asleep_minutes = n.asleep_minutes
        r.bedtime = f"{n.start_at.astimezone(tz):%H:%M}"
        r.wake_time = f"{n.end_at.astimezone(tz):%H:%M}"
        r.deep_minutes, r.rem_minutes = n.deep_minutes, n.rem_minutes
        r.awake_minutes = n.awake_minutes

    for m in session.scalars(
        select(DailyMetrics).where(
            DailyMetrics.local_date >= since, DailyMetrics.local_date <= until
        )
    ):
        r = rows[m.local_date]
        r.steps, r.resting_hr, r.kcal_burned = m.steps, m.resting_hr, _round(m.kcal_burned)

    maximum = analysis.hr_max(session, until)
    for t in session.scalars(
        select(TrainingSession)
        .options(selectinload(TrainingSession.sets))
        .where(
            TrainingSession.started_at >= datetime.combine(since, time.min, tzinfo=tz),
            TrainingSession.started_at
            < datetime.combine(until + timedelta(days=1), time.min, tzinfo=tz),
        )
        .order_by(TrainingSession.started_at)
    ):
        r = rows[training.local_date(t.started_at)]
        detail = training.split_for(t)
        if t.duration_minutes:
            detail += f", {t.duration_minutes} min"
        r.training.append(f"{t.workout_name} ({detail})")
        r.sets += len(t.sets)
        r.volume_kg = round(r.volume_kg + sum(training.set_volume(s) for s in t.sets), 1)
        r.zone2_minutes += analysis.session_zone2(session, t, maximum)

    tracked = nutrition.days(session, since - timedelta(days=1), until)
    nutrition.flag_days(tracked, until)
    for d in tracked:
        if d.date in rows:
            r = rows[d.date]
            r.kcal, r.protein_g = _round(d.kcal), _round(d.protein_g)
            r.nutrition_flags = list(d.flags)

    for w in nutrition.weights(session, since):
        if w.date in rows:
            rows[w.date].weight_kg = w.kg

    for day, e in analysis.first_events(session, since, until).items():
        rows[day].first_event = f"{e.starts_at.astimezone(tz):%H:%M} {e.title}"

    done: dict[date, int] = defaultdict(int)
    for at in session.scalars(
        select(Task.completed_at).where(
            Task.status == TaskStatus.done,
            Task.completed_at >= datetime.combine(since, time.min, tzinfo=tz),
        )
    ):
        day = at.astimezone(tz).date()
        if day in rows:
            done[day] += 1
    for day, count in done.items():
        rows[day].tasks_done = count

    for entry in session.scalars(
        select(JournalEntry).where(
            JournalEntry.local_date >= since, JournalEntry.local_date <= until
        )
    ):
        rows[entry.local_date].mood = entry.mood
        rows[entry.local_date].energy = entry.energy

    return [rows[d] for d in sorted(rows)]
