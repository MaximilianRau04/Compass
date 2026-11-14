"""The Compass workout logger: sessions logged on the phone.

The phone keeps the running session and sends all of it after every change, so a lost connection
in the gym costs nothing: the same client id updates the same session, and its sets are replaced
by what the phone sends. A session started from a template gets each exercise's last working sets
and its progression target. The template is the workout built in Compass with that name, or else
the last session with that name.
"""

from datetime import date, datetime, timedelta
from typing import Annotated

from pydantic import AwareDatetime, BaseModel, Field
from sqlalchemy import any_, delete, func, select
from sqlalchemy.orm import Session

from app.models.training import (
    Exercise,
    ExerciseAlias,
    ExerciseSet,
    TrainingSession,
    WorkoutTemplate,
)
from app.services import health
from app.services.clock import local_tz, utc_now
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


def _clean(name: str) -> str:
    return " ".join(name.split())


def find_exercise(session: Session, exercise_id: int | None, name: str) -> Exercise | None:
    """By id, else by name or alias (any case)."""
    if exercise_id is not None and (found := session.get(Exercise, exercise_id)):
        return found
    name = _clean(name)
    return session.scalar(
        select(Exercise)
        .outerjoin(ExerciseAlias)
        .where(
            (func.lower(Exercise.name) == name.lower())
            | (func.lower(ExerciseAlias.alias) == name.lower())
        )
        .limit(1)
    )


def resolve_exercise(session: Session, item: LoggedExercise) -> Exercise:
    """By id, else by name or alias (any case), else a new exercise."""
    if found := find_exercise(session, item.exercise_id, item.name):
        return found
    name = _clean(item.name)
    exercise = Exercise(name=name, bodyweight=all(s.weight_kg is None for s in item.sets))
    session.add(exercise)
    session.flush()
    return exercise


def save(session: Session, data: LoggedSession) -> TrainingSession:
    if data.ended_at and data.ended_at < data.started_at:
        raise LogError("ended_at is before started_at")
    # A session entered afterwards can lie in the past, never in the future (some clock slack).
    if data.started_at > utc_now() + timedelta(minutes=10):
        raise LogError("the session starts in the future")
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


# --- Templates built in Compass --------------------------------------------------------------

REST_DEFAULT = 90


class TemplateItem(BaseModel):
    exercise_id: int | None = None
    name: str = Field(min_length=1, max_length=200)
    sets: int = Field(3, ge=1, le=20, description="Planned sets")
    rest_seconds: int = Field(REST_DEFAULT, ge=0, le=900, description="Rest after each set")


class TemplateData(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    exercises: list[TemplateItem] = Field(default_factory=list, max_length=40)
    weekdays: list[Annotated[int, Field(ge=0, le=6)]] = Field(
        default_factory=list, max_length=7, description="Days it is planned on, 0 = Monday"
    )


def saved_template(session: Session, name: str) -> WorkoutTemplate | None:
    return session.scalar(
        select(WorkoutTemplate).where(func.lower(WorkoutTemplate.name) == _clean(name).lower())
    )


def list_templates(session: Session) -> list[tuple[WorkoutTemplate, datetime | None]]:
    """Every template with the last session of the same name, most recently trained first."""
    last = dict(
        session.execute(
            select(
                func.lower(TrainingSession.workout_name), func.max(TrainingSession.started_at)
            ).group_by(func.lower(TrainingSession.workout_name))
        ).all()
    )
    rows = [(t, last.get(t.name.lower())) for t in session.scalars(select(WorkoutTemplate))]
    # Never trained ones first (just built), then by the last session.
    return sorted(
        rows, key=lambda r: (r[1] is not None, -(r[1].timestamp() if r[1] else 0), r[0].name)
    )


def save_template(
    session: Session, data: TemplateData, template: WorkoutTemplate | None = None
) -> WorkoutTemplate:
    name = _clean(data.name)
    other = saved_template(session, name)
    if other is not None and other is not template:
        raise LogError("a workout with this name exists")
    items = []
    for item in data.exercises:
        known = find_exercise(session, item.exercise_id, item.name)
        items.append(
            {
                "exercise_id": known.id if known else None,
                "name": known.name if known else _clean(item.name),
                "sets": item.sets,
                "rest_seconds": item.rest_seconds,
            }
        )
    if template is None:
        template = WorkoutTemplate(name=name)
        session.add(template)
    template.name = name
    template.exercises = items
    template.weekdays = sorted(set(data.weekdays))
    session.flush()
    return template


def planned_for(session: Session, day: date) -> list[WorkoutTemplate]:
    """The workouts planned on the weekday of `day`, by name."""
    return list(
        session.scalars(
            select(WorkoutTemplate)
            .where(any_(WorkoutTemplate.weekdays) == day.weekday())
            .order_by(WorkoutTemplate.name)
        )
    )


def trained_on(session: Session, day: date) -> set[str]:
    """Lower-case workout names of the sessions started on `day` (local)."""
    start = datetime.combine(day, datetime.min.time(), tzinfo=local_tz())
    return {
        name.lower()
        for name in session.scalars(
            select(TrainingSession.workout_name).where(
                TrainingSession.started_at >= start,
                TrainingSession.started_at < start + timedelta(days=1),
            )
        )
        if name
    }


def template_items(
    session: Session, template: WorkoutTemplate
) -> list[tuple[Exercise | None, dict]]:
    """Each planned exercise with its row (None for one never trained yet). Looked up again on
    every read, so a renamed or merged exercise is still found."""
    return [
        (find_exercise(session, item.get("exercise_id"), item["name"]), item)
        for item in template.exercises
    ]
