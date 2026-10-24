from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request, status
from sqlalchemy import select
from starlette.concurrency import run_in_threadpool

from app.api.deps import SessionDep
from app.ingestion import gymday
from app.models.training import Exercise, TrainingSession
from app.schemas.training import (
    DoneSetRead,
    ExerciseRead,
    ExerciseUpdate,
    ImportResult,
    MergeRequest,
    ProgressionRead,
    ProgressPointRead,
    SessionBrief,
    SessionDetail,
    SessionExercise,
    SetRead,
    SuggestionRead,
    TemplateExercise,
    TemplateRead,
    TrainingSummaryRead,
    WeekRead,
    WorkoutNameRead,
)
from app.services import analysis, progression, training, workout_log
from app.services.clock import local_today
from app.services.training import TrainingError
from app.services.workout_log import LogError, LoggedSession

router = APIRouter(prefix="/training", tags=["training"])


def brief(s: TrainingSession) -> SessionBrief:
    return SessionBrief(
        id=s.id,
        started_at=s.started_at,
        workout_name=s.workout_name,
        split=training.split_for(s),
        exercises=len({x.exercise_id for x in s.sets}),
        sets=len(s.sets),
        volume_kg=round(sum(training.set_volume(x) for x in s.sets)),
        duration_minutes=s.duration_minutes,
        source=s.source,
        activity=s.activity,
        hr_avg=s.hr_avg,
        hr_max=s.hr_max,
    )


def _exercise(session, exercise_id: int) -> Exercise:
    exercise = session.get(Exercise, exercise_id)
    if exercise is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "exercise not found")
    return exercise


@router.post("/import", response_model=ImportResult)
async def import_gymday(request: Request, session: SessionDep):
    """Import a Gym Day strength export. The CSV is the raw request body."""
    if int(request.headers.get("content-length") or 0) > gymday.MAX_BYTES:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "file is larger than 5 MB")
    data = await request.body()

    def run() -> dict:
        result = gymday.import_csv(session, data)
        session.commit()
        return result

    try:
        return await run_in_threadpool(run)
    except gymday.GymDayImportError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc


@router.get("/summary", response_model=TrainingSummaryRead)
def summary(session: SessionDep, weeks: Annotated[int, Query(ge=1, le=104)] = 12):
    s = training.summary(session, weeks)
    return TrainingSummaryRead(
        since=s.since,
        sessions=s.sessions,
        sets=s.sets,
        volume_kg=s.volume_kg,
        this_week_sessions=s.this_week_sessions,
        last_session=brief(s.last_session) if s.last_session else None,
        weeks=[WeekRead(**w.__dict__) for w in s.weeks],
        split=s.split,
    )


@router.get("/sessions", response_model=list[SessionBrief])
def sessions(session: SessionDep, limit: Annotated[int, Query(ge=1, le=200)] = 20):
    maximum = analysis.hr_max(session)
    out = []
    for s in training.recent_sessions(session, limit):
        item = brief(s)
        if s.hr_avg is not None:
            item.zone2_minutes = analysis.session_zone2(session, s, maximum)
        out.append(item)
    return out


@router.get("/sessions/{session_id}", response_model=SessionDetail)
def session_detail(session_id: int, session: SessionDep):
    s = training.get_session(session, session_id)
    if s is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "session not found")
    groups: dict[int, SessionExercise] = {}
    for x in s.sets:
        group = groups.setdefault(
            x.exercise_id,
            SessionExercise(
                exercise_id=x.exercise_id,
                name=x.exercise.name,
                bodyweight=x.exercise.bodyweight,
                sets=[],
            ),
        )
        group.sets.append(
            SetRead(
                set_index=x.set_index,
                weight_kg=float(x.weight_kg) if x.weight_kg is not None else None,
                reps=x.reps,
                rir=x.rir,
                e1rm=training.e1rm(x.weight_kg, x.reps),
            )
        )
    for group in groups.values():
        group.sets.sort(key=lambda r: r.set_index)
    return SessionDetail(**brief(s).model_dump(), exercise_sets=list(groups.values()))


@router.get("/exercises", response_model=list[ExerciseRead])
def exercises(session: SessionDep):
    return [
        ExerciseRead(
            id=r.exercise.id,
            name=r.exercise.name,
            muscle_group=r.exercise.muscle_group,
            bodyweight=r.exercise.bodyweight,
            rep_min=progression.rep_range(r.exercise)[0],
            rep_max=progression.rep_range(r.exercise)[1],
            weight_step=float(progression.rep_range(r.exercise)[2]),
            aliases=sorted(a.alias for a in r.exercise.aliases),
            sessions=r.sessions,
            sets=r.sets,
            last_at=r.last_at,
            best_e1rm=r.best_e1rm,
            best_weight=r.best_weight,
            max_reps=r.max_reps,
        )
        for r in training.exercise_stats(session)
    ]


@router.get("/exercises/{exercise_id}/progress", response_model=list[ProgressPointRead])
def exercise_progress(
    exercise_id: int, session: SessionDep, weeks: Annotated[int | None, Query(ge=1, le=520)] = None
):
    since = local_today() - timedelta(weeks=weeks) if weeks else None
    return [p.__dict__ for p in training.progress(session, _exercise(session, exercise_id), since)]


@router.patch("/exercises/{exercise_id}", response_model=ExerciseRead)
def update_exercise(exercise_id: int, data: ExerciseUpdate, session: SessionDep):
    exercise = _exercise(session, exercise_id)
    changes = data.model_dump(exclude_unset=True)
    new_name = changes.get("name")
    taken = (
        new_name
        and new_name != exercise.name
        and session.scalar(select(Exercise).where(Exercise.name == new_name))
    )
    if taken:
        raise HTTPException(status.HTTP_409_CONFLICT, "an exercise with this name exists")
    for field, value in changes.items():
        if field == "name" and value is None:
            continue
        setattr(exercise, field, value)
    if (exercise.rep_min or 0) and (exercise.rep_max or 0) and exercise.rep_min > exercise.rep_max:
        raise HTTPException(422, "rep_min is above rep_max")
    session.commit()
    return next(e for e in exercises(session) if e.id == exercise_id)


@router.post("/exercises/{exercise_id}/merge", response_model=ExerciseRead)
def merge_exercise(exercise_id: int, data: MergeRequest, session: SessionDep):
    source, target = _exercise(session, exercise_id), _exercise(session, data.into)
    try:
        training.merge_exercises(session, source, target)
    except TrainingError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    session.commit()
    return next(e for e in exercises(session) if e.id == target.id)


def suggestion_read(s: progression.Suggestion) -> SuggestionRead:
    return SuggestionRead(
        exercise_id=s.exercise.id,
        name=s.exercise.name,
        bodyweight=s.exercise.bodyweight,
        last_date=s.last_date,
        last_sets=[DoneSetRead(**x.__dict__) for x in s.last_sets],
        last_set_count=s.last_set_count,
        rep_min=s.rep_min,
        rep_max=s.rep_max,
        weight_step=s.weight_step,
        action=s.action,
        weight_kg=s.weight_kg,
        reps=s.reps,
        rir_known=s.rir_known,
        same_sessions=s.same_sessions,
        stagnant=s.stagnant,
    )


@router.get("/progression", response_model=ProgressionRead)
def progression_overview(session: SessionDep, weeks: Annotated[int, Query(ge=1, le=52)] = 8):
    found = progression.suggestions(session, weeks)
    return ProgressionRead(
        suggestions=[suggestion_read(s) for s in found],
        stagnant=[suggestion_read(s) for s in found if s.stagnant],
    )


# --- Workout logger --------------------------------------------------------------------------


@router.get("/log/workouts", response_model=list[WorkoutNameRead])
def logger_workouts(session: SessionDep):
    """Workout names to start from, most recently trained first."""
    return [WorkoutNameRead(name=n, last_at=at) for n, at in workout_log.workout_names(session)]


@router.get("/log/template", response_model=TemplateRead)
def logger_template(session: SessionDep, workout: str = Query(min_length=1, max_length=120)):
    """The exercises of the last session with this name, each with its progression target."""
    exercises = workout_log.template(session, workout)
    targets = progression.for_exercises(session, exercises)
    return TemplateRead(
        workout_name=workout,
        exercises=[
            TemplateExercise(
                exercise_id=e.id,
                name=e.name,
                bodyweight=e.bodyweight,
                suggestion=suggestion_read(targets[e.id]) if e.id in targets else None,
            )
            for e in exercises
        ],
    )


@router.get("/log/exercises/{exercise_id}", response_model=TemplateExercise)
def logger_exercise(exercise_id: int, session: SessionDep):
    """One exercise added during a session, with its target."""
    exercise = _exercise(session, exercise_id)
    target = progression.for_exercises(session, [exercise]).get(exercise.id)
    return TemplateExercise(
        exercise_id=exercise.id,
        name=exercise.name,
        bodyweight=exercise.bodyweight,
        suggestion=suggestion_read(target) if target else None,
    )


@router.post("/log", response_model=SessionBrief)
def logger_save(data: LoggedSession, session: SessionDep):
    """Save the running (or finished) session from the phone. Sending it again updates it."""
    try:
        t = workout_log.save(session, data)
    except LogError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    session.commit()
    return brief(training.get_session(session, t.id))


@router.post("/log/{client_id}/discard", status_code=status.HTTP_204_NO_CONTENT)
def logger_discard(client_id: str, session: SessionDep):
    """Throw away a session started by mistake (only logger sessions)."""
    if not workout_log.discard(session, client_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no logged session with this id")
    session.commit()
