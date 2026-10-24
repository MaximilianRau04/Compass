"""Double progression per exercise, and exercises that stagnate.

Each exercise has a rep range (rep_min..rep_max) and a weight step. The working sets of a session
are the sets at its top weight (lighter warm-up sets do not count). When every working set reached
rep_max with at most MAX_RIR reps in reserve, the next target is the weight plus the step at
rep_min.
Otherwise the weight stays and the target is one rep more than the weakest working set, up to
rep_max. Sets without a logged RIR (the Gym Day export has none) count as fulfilled; the suggestion
says so (rir_known).

An exercise stagnates when its last STAGNATION_SESSIONS sessions had the same top weight and the
same reps in every working set.
"""

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.training import Exercise, ExerciseSet, TrainingSession
from app.services.clock import local_today, local_tz

DEFAULT_REP_MIN = 8
DEFAULT_REP_MAX = 12
DEFAULT_STEP = Decimal("2.5")
MAX_RIR = 2
STAGNATION_SESSIONS = 4


@dataclass
class DoneSet:
    weight_kg: float | None
    reps: int | None
    rir: int | None


@dataclass
class Suggestion:
    exercise: Exercise
    last_date: date
    last_sets: list[DoneSet]  # working sets of the last session
    last_set_count: int  # all sets of the last session, warm-ups included
    rep_min: int
    rep_max: int
    weight_step: float
    action: str  # increase | reps
    weight_kg: float | None  # target; None for a bodyweight exercise
    reps: int
    rir_known: bool
    same_sessions: int  # how many sessions in a row had these working sets
    stagnant: bool


def rep_range(exercise: Exercise) -> tuple[int, int, Decimal]:
    rep_min = exercise.rep_min or DEFAULT_REP_MIN
    rep_max = max(exercise.rep_max or DEFAULT_REP_MAX, rep_min)
    return rep_min, rep_max, exercise.weight_step or DEFAULT_STEP


def working_sets(sets: list[ExerciseSet]) -> list[ExerciseSet]:
    """The sets at the session's top weight; all sets of a bodyweight exercise."""
    weights = [s.weight_kg for s in sets if s.weight_kg is not None]
    if not weights:
        return [s for s in sets if s.reps]
    top = max(weights)
    return [s for s in sets if s.weight_kg == top and s.reps]


def _signature(sets: list[ExerciseSet]) -> tuple:
    work = working_sets(sets)
    top = work[0].weight_kg if work else None
    return top, tuple(sorted((s.reps or 0 for s in work), reverse=True))


def history(
    session: Session, exercise_ids: list[int] | None = None, since: date | None = None
) -> dict[int, list[tuple[datetime, list[ExerciseSet]]]]:
    """Sets per exercise and session, oldest session first."""
    stmt = (
        select(ExerciseSet, TrainingSession.started_at)
        .join(TrainingSession)
        .order_by(TrainingSession.started_at, ExerciseSet.set_index)
    )
    if exercise_ids is not None:
        stmt = stmt.where(ExerciseSet.exercise_id.in_(exercise_ids))
    if since is not None:
        start = datetime.combine(since, time.min, tzinfo=local_tz())
        stmt = stmt.where(TrainingSession.started_at >= start)
    per: dict[int, dict[int, tuple[datetime, list[ExerciseSet]]]] = defaultdict(dict)
    for s, started_at in session.execute(stmt).all():
        per[s.exercise_id].setdefault(s.session_id, (started_at, []))[1].append(s)
    return {ex: sorted(sessions.values(), key=lambda x: x[0]) for ex, sessions in per.items()}


def suggest(
    exercise: Exercise, sessions: list[tuple[datetime, list[ExerciseSet]]]
) -> Suggestion | None:
    """The next target from the last session that has working sets."""
    sessions = [(at, sets) for at, sets in sessions if working_sets(sets)]
    if not sessions:
        return None
    last_at, last = sessions[-1]
    work = working_sets(last)
    rep_min, rep_max, step = rep_range(exercise)
    reps = [s.reps or 0 for s in work]
    rirs = [s.rir for s in work]
    reached = all(r >= rep_max for r in reps) and all(r is None or r <= MAX_RIR for r in rirs)
    top = work[0].weight_kg

    if top is None:
        # Bodyweight: more reps until the top of the range, then add the step as extra load.
        action, weight, target = (
            ("increase", float(step), rep_min)
            if reached
            else (
                "reps",
                None,
                min(rep_max, max(rep_min, min(reps) + 1)),
            )
        )
    elif reached:
        action, weight, target = "increase", float(top + step), rep_min
    else:
        action, weight, target = "reps", float(top), min(rep_max, max(rep_min, min(reps) + 1))

    signature = _signature(last)
    same = 0
    for _, sets in reversed(sessions):
        if _signature(sets) != signature:
            break
        same += 1
    return Suggestion(
        exercise=exercise,
        last_date=last_at.astimezone(local_tz()).date(),
        last_sets=[
            DoneSet(float(s.weight_kg) if s.weight_kg is not None else None, s.reps, s.rir)
            for s in work
        ],
        last_set_count=len(last),
        rep_min=rep_min,
        rep_max=rep_max,
        weight_step=float(step),
        action=action,
        weight_kg=weight,
        reps=target,
        rir_known=all(r is not None for r in rirs),
        same_sessions=same,
        stagnant=same >= STAGNATION_SESSIONS,
    )


def suggestions(session: Session, weeks: int = 8) -> list[Suggestion]:
    """A suggestion for every exercise trained in the last `weeks` weeks, most recent first."""
    recent = history(session, since=local_today() - timedelta(weeks=weeks))
    if not recent:
        return []
    # The stagnation count needs the sessions before the window too.
    full = history(session, exercise_ids=list(recent))
    exercises = {
        e.id: e for e in session.scalars(select(Exercise).where(Exercise.id.in_(list(recent))))
    }
    out = [s for ex_id, sessions in full.items() if (s := suggest(exercises[ex_id], sessions))]
    out.sort(key=lambda s: (s.last_date, s.exercise.name), reverse=True)
    return out


def for_exercises(session: Session, exercises: list[Exercise]) -> dict[int, Suggestion]:
    found = history(session, exercise_ids=[e.id for e in exercises])
    by_id = {e.id: e for e in exercises}
    return {ex_id: s for ex_id, sessions in found.items() if (s := suggest(by_id[ex_id], sessions))}
