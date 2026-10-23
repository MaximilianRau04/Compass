"""Training statistics over the imported sessions, shared by the REST API and the MCP server."""

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from sqlalchemy import func, or_, select, update
from sqlalchemy.orm import Session, selectinload

from app.models.training import Exercise, ExerciseAlias, ExerciseSet, TrainingSession
from app.services.clock import local_today, local_tz
from app.services.health import STRENGTH, WATCH_SESSION

# Epley gets unreliable for high rep sets, so the estimated 1RM only uses sets up to 12 reps.
E1RM_MAX_REPS = 12
SPLITS = ("push", "pull", "legs", "other", "sport")


class TrainingError(ValueError):
    pass


def split_for(s: TrainingSession) -> str:
    """Push, pull, legs, other for strength sessions; "sport" for a watch workout like
    bouldering or a run."""
    if s.source == WATCH_SESSION and s.activity not in STRENGTH:
        return "sport"
    return split_of(s.workout_name)


def split_of(workout_name: str) -> str:
    name = workout_name.lower()
    if "push" in name:
        return "push"
    if "pull" in name:
        return "pull"
    if "leg" in name or "bein" in name:
        return "legs"
    return "other"


def e1rm(weight: Decimal | None, reps: int | None) -> float | None:
    """Estimated one-rep max (Epley). None for bodyweight or high-rep sets."""
    if weight is None or not reps or reps > E1RM_MAX_REPS:
        return None
    if reps == 1:
        return float(weight)
    return round(float(weight) * (1 + reps / 30), 1)


def set_volume(s: ExerciseSet) -> float:
    return float(s.weight_kg) * s.reps if s.weight_kg is not None and s.reps else 0.0


def local_date(value: datetime) -> date:
    return value.astimezone(local_tz()).date()


def week_start(day: date) -> date:
    return day - timedelta(days=day.weekday())


# --- Queries ---------------------------------------------------------------------------------


def _sessions_since(session: Session, since: date | None) -> list[TrainingSession]:
    stmt = select(TrainingSession).options(selectinload(TrainingSession.sets))
    if since is not None:
        stmt = stmt.where(
            TrainingSession.started_at >= datetime.combine(since, time.min, tzinfo=local_tz())
        )
    return list(session.scalars(stmt.order_by(TrainingSession.started_at)))


@dataclass
class Week:
    week_start: date
    sessions: int = 0
    sets: int = 0
    volume_kg: float = 0.0


@dataclass
class Summary:
    since: date
    sessions: int
    sets: int
    volume_kg: float
    this_week_sessions: int
    last_session: TrainingSession | None
    weeks: list[Week]
    split: dict[str, int] = field(default_factory=dict)


def summary(session: Session, weeks: int = 12, today: date | None = None) -> Summary:
    today = today or local_today()
    first_week = week_start(today) - timedelta(weeks=weeks - 1)
    found = _sessions_since(session, first_week)

    starts = [first_week + timedelta(weeks=i) for i in range(weeks)]
    by_week = {start: Week(start) for start in starts}
    split: Counter[str] = Counter({s: 0 for s in SPLITS})
    for s in found:
        week = by_week.get(week_start(local_date(s.started_at)))
        if week is None:  # dated after the current week
            continue
        week.sessions += 1
        week.sets += len(s.sets)
        week.volume_kg += sum(set_volume(x) for x in s.sets)
        split[split_for(s)] += 1
    for week in by_week.values():
        week.volume_kg = round(week.volume_kg)

    last = session.scalar(select(TrainingSession).order_by(TrainingSession.started_at.desc()))
    return Summary(
        since=first_week,
        sessions=sum(w.sessions for w in by_week.values()),
        sets=sum(w.sets for w in by_week.values()),
        volume_kg=round(sum(w.volume_kg for w in by_week.values())),
        this_week_sessions=by_week[week_start(today)].sessions,
        last_session=last,
        weeks=list(by_week.values()),
        split=dict(split),
    )


def recent_sessions(session: Session, limit: int = 20) -> list[TrainingSession]:
    stmt = (
        select(TrainingSession)
        .options(selectinload(TrainingSession.sets))
        .order_by(TrainingSession.started_at.desc())
        .limit(limit)
    )
    return list(session.scalars(stmt))


def get_session(session: Session, session_id: int) -> TrainingSession | None:
    return session.get(TrainingSession, session_id, options=[selectinload(TrainingSession.sets)])


@dataclass
class ExerciseStats:
    exercise: Exercise
    sessions: int
    sets: int
    last_at: datetime | None
    best_e1rm: float | None
    best_weight: float | None
    max_reps: int | None


def exercise_stats(session: Session) -> list[ExerciseStats]:
    exercises = session.scalars(
        select(Exercise).options(selectinload(Exercise.aliases)).order_by(Exercise.name)
    ).all()
    rows = session.execute(
        select(ExerciseSet, TrainingSession.started_at).join(TrainingSession)
    ).all()
    per: dict[int, list[tuple[ExerciseSet, datetime]]] = defaultdict(list)
    for s, started_at in rows:
        per[s.exercise_id].append((s, started_at))

    result = []
    for exercise in exercises:
        sets = per.get(exercise.id, [])
        e1rms = [v for s, _ in sets if (v := e1rm(s.weight_kg, s.reps)) is not None]
        weights = [float(s.weight_kg) for s, _ in sets if s.weight_kg is not None]
        reps = [s.reps for s, _ in sets if s.reps]
        result.append(
            ExerciseStats(
                exercise=exercise,
                sessions=len({s.session_id for s, _ in sets}),
                sets=len(sets),
                last_at=max((at for _, at in sets), default=None),
                best_e1rm=max(e1rms, default=None),
                best_weight=max(weights, default=None),
                max_reps=max(reps, default=None),
            )
        )
    # Most trained first: that is what the progression picker should offer.
    result.sort(key=lambda r: (-r.sessions, r.exercise.name))
    return result


@dataclass
class ProgressPoint:
    date: date
    session_id: int
    workout_name: str
    sets: int
    top_weight: float | None
    best_e1rm: float | None
    max_reps: int | None
    volume_kg: float


def find_exercise(session: Session, name: str) -> Exercise:
    """Exact (case-insensitive) name or alias first, then a unique partial match."""
    needle = name.strip().lower()
    exact = session.scalar(
        select(Exercise)
        .outerjoin(ExerciseAlias)
        .where(or_(func.lower(Exercise.name) == needle, func.lower(ExerciseAlias.alias) == needle))
    )
    if exact:
        return exact
    matches = (
        session.scalars(
            select(Exercise)
            .outerjoin(ExerciseAlias)
            .where(
                or_(
                    func.lower(Exercise.name).contains(needle),
                    func.lower(ExerciseAlias.alias).contains(needle),
                )
            )
        )
        .unique()
        .all()
    )
    if len(matches) == 1:
        return matches[0]
    if not matches:
        raise TrainingError(f"No exercise matches {name!r}.")
    names = ", ".join(sorted(m.name for m in matches)[:10])
    raise TrainingError(f"{name!r} matches several exercises: {names}.")


def progress(
    session: Session, exercise: Exercise, since: date | None = None
) -> list[ProgressPoint]:
    stmt = (
        select(ExerciseSet, TrainingSession)
        .join(TrainingSession)
        .where(ExerciseSet.exercise_id == exercise.id)
        .order_by(TrainingSession.started_at, ExerciseSet.set_index)
    )
    if since is not None:
        stmt = stmt.where(
            TrainingSession.started_at >= datetime.combine(since, time.min, tzinfo=local_tz())
        )
    per: dict[int, tuple[TrainingSession, list[ExerciseSet]]] = {}
    for s, ts in session.execute(stmt).all():
        per.setdefault(ts.id, (ts, []))[1].append(s)

    points = []
    for ts, sets in per.values():
        weights = [float(s.weight_kg) for s in sets if s.weight_kg is not None]
        e1rms = [v for s in sets if (v := e1rm(s.weight_kg, s.reps)) is not None]
        reps = [s.reps for s in sets if s.reps]
        points.append(
            ProgressPoint(
                date=local_date(ts.started_at),
                session_id=ts.id,
                workout_name=ts.workout_name,
                sets=len(sets),
                top_weight=max(weights, default=None),
                best_e1rm=max(e1rms, default=None),
                max_reps=max(reps, default=None),
                volume_kg=round(sum(set_volume(s) for s in sets)),
            )
        )
    return points


# --- Mapping ---------------------------------------------------------------------------------


def merge_exercises(session: Session, source: Exercise, target: Exercise) -> Exercise:
    """Fold `source` into `target`, e.g. after renaming an exercise in Gym Day. Sets and export
    names (aliases) move over, so the progression continues in one line."""
    if source.id == target.id:
        raise TrainingError("An exercise cannot be merged into itself.")

    def set_keys(exercise: Exercise) -> set[tuple[int, int]]:
        stmt = select(ExerciseSet.session_id, ExerciseSet.set_index).where(
            ExerciseSet.exercise_id == exercise.id
        )
        return {(row.session_id, row.set_index) for row in session.execute(stmt)}

    # Two sets with the same number in the same session cannot both belong to one exercise.
    if set_keys(source) & set_keys(target):
        raise TrainingError(
            f"{source.name!r} and {target.name!r} were both trained in the same session with the "
            "same set numbers, so they cannot be merged."
        )
    session.execute(
        update(ExerciseSet)
        .where(ExerciseSet.exercise_id == source.id)
        .values(exercise_id=target.id)
    )
    session.execute(
        update(ExerciseAlias)
        .where(ExerciseAlias.exercise_id == source.id)
        .values(exercise_id=target.id)
    )
    # Reload both, otherwise deleting `source` would cascade to the aliases it no longer owns.
    session.expire(source)
    session.expire(target)
    session.delete(source)
    session.flush()
    return target
