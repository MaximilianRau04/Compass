"""The Compass workout logger: sessions logged on the phone.

The phone keeps the running session and sends all of it after every change, so a lost connection
in the gym costs nothing: the same client id updates the same session, and its sets are replaced
by what the phone sends. A session started from a template (the last session with that workout
name) gets each exercise's last working sets and its progression target.
"""

from datetime import datetime, timedelta

from pydantic import AwareDatetime, BaseModel, Field
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.models.training import Exercise, ExerciseAlias, ExerciseSet, TrainingSession
from app.services import health
from app.services.clock import local_tz
from app.services.health import LOGGER_SESSION


class LogError(ValueError):
    pass


class LoggedSet(BaseModel):
    weight_kg: float | None = Field(None, ge=0, le=1000, description="None for bodyweight")
    reps: int = Field(ge=0, le=200)
    rir: int | None = Field(None, ge=0, le=10, description="Reps in reserve")


class LoggedExercise(BaseModel):
    exercise_id: int | None = None
    name: str = Field(min_length=1, max_length=200)
    sets: list[LoggedSet] = Field(default_factory=list, max_length=50)


class LoggedSession(BaseModel):
    client_id: str = Field(pattern=r"^[A-Za-z0-9-]{8,36}$")
    workout_name: str = Field(min_length=1, max_length=120)
    started_at: AwareDatetime
    ended_at: AwareDatetime | None = None
    exercises: list[LoggedExercise] = Field(default_factory=list, max_length=40)


def resolve_exercise(session: Session, item: LoggedExercise) -> Exercise:
    """By id, else by name or alias (any case), else a new exercise."""
    if item.exercise_id is not None and (found := session.get(Exercise, item.exercise_id)):
        return found
    name = " ".join(item.name.split())
    found = session.scalar(
        select(Exercise)
        .outerjoin(ExerciseAlias)
        .where(
            (func.lower(Exercise.name) == name.lower())
            | (func.lower(ExerciseAlias.alias) == name.lower())
        )
    )
    if found:
        return found
    exercise = Exercise(name=name, bodyweight=all(s.weight_kg is None for s in item.sets))
    session.add(exercise)
    session.flush()
    return exercise


def save(session: Session, data: LoggedSession) -> TrainingSession:
    if data.ended_at and data.ended_at < data.started_at:
        raise LogError("ended_at is before started_at")
    t = session.scalar(select(TrainingSession).where(TrainingSession.client_id == data.client_id))
    if t is None:
        t = TrainingSession(client_id=data.client_id, source=LOGGER_SESSION)
        session.add(t)
    elif t.source != LOGGER_SESSION:
        raise LogError("this session was not logged in Compass")
    t.workout_name = " ".join(data.workout_name.split())
    # A session is unique by start and name; another one at the same second (two quick starts,
    # a Gym Day import) moves this one by a second instead of failing.
    start = data.started_at
    with session.no_autoflush:
        while session.scalar(
            select(TrainingSession.id).where(
                TrainingSession.started_at == start,
                TrainingSession.workout_name == t.workout_name,
                TrainingSession.client_id.is_distinct_from(data.client_id),
            )
        ):
            start += timedelta(seconds=1)
    t.started_at = start
    t.ended_at = data.ended_at
    t.duration_minutes = (
        round((data.ended_at - data.started_at).total_seconds() / 60) if data.ended_at else None
    )
    session.flush()

    session.execute(delete(ExerciseSet).where(ExerciseSet.session_id == t.id))
    counters: dict[int, int] = {}
    for item in data.exercises:
        if not item.sets:
            continue
        exercise = resolve_exercise(session, item)
        for logged in item.sets:
            counters[exercise.id] = counters.get(exercise.id, 0) + 1
            session.add(
                ExerciseSet(
                    session_id=t.id,
                    exercise_id=exercise.id,
                    set_index=counters[exercise.id],
                    weight_kg=logged.weight_kg,
                    reps=logged.reps,
                    rir=logged.rir,
                    raw={"logger": True},
                )
            )
    session.flush()
    session.expire(t, ["sets"])
    # The watch's recording of it gives the heart rate.
    day = data.started_at.astimezone(local_tz()).date()
    health.match_watch_sessions(session, day, day)
    return t


def discard(session: Session, client_id: str) -> bool:
    t = session.scalar(select(TrainingSession).where(TrainingSession.client_id == client_id))
    if t is None or t.source != LOGGER_SESSION:
        return False
    session.delete(t)
    session.flush()
    return True


def workout_names(session: Session, limit: int = 12) -> list[tuple[str, datetime]]:
    """Workout names of sessions with sets, most recently trained first."""
    rows = session.execute(
        select(TrainingSession.workout_name, func.max(TrainingSession.started_at).label("last"))
        .join(ExerciseSet)
        .group_by(TrainingSession.workout_name)
        .order_by(func.max(TrainingSession.started_at).desc())
        .limit(limit)
    )
    return [(name, last) for name, last in rows]


def template(session: Session, workout_name: str) -> list[Exercise]:
    """The exercises of the last session with this workout name, in the order they were done."""
    last = session.scalar(
        select(TrainingSession)
        .join(ExerciseSet)
        .where(func.lower(TrainingSession.workout_name) == workout_name.strip().lower())
        .order_by(TrainingSession.started_at.desc())
        .limit(1)
    )
    if last is None:
        return []
    ordered: dict[int, Exercise] = {}
    for s in sorted(last.sets, key=lambda x: x.id):
        ordered.setdefault(s.exercise_id, s.exercise)
    return list(ordered.values())
