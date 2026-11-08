"""Tools for strength training."""

from datetime import timedelta
from typing import Annotated

from mcp.server.mcpserver.exceptions import ToolError
from pydantic import Field

from app.mcp.core import READ, mcp
from app.mcp.db import session_scope
from app.mcp.schemas import (
    ExerciseProgressOut,
    ProgressionOut,
    ProgressOut,
    TrainingSummaryOut,
    WeekOut,
    Zone2Out,
    session_out,
    target_out,
)
from app.services import analysis, progression, training
from app.services.clock import local_today


@mcp.tool(title="Training summary", annotations=READ)
def training_summary(
    weeks: Annotated[int, Field(ge=1, le=52, description="How many weeks back")] = 4,
) -> TrainingSummaryOut:
    """Strength training overview: sessions, sets and volume per week, split distribution
    (push/pull/legs) and the most recent sessions."""
    with session_scope() as session:
        s = training.summary(session, weeks)
        return TrainingSummaryOut(
            since=s.since,
            sessions=s.sessions,
            sets=s.sets,
            volume_kg=s.volume_kg,
            this_week_sessions=s.this_week_sessions,
            split=s.split,
            weeks=[WeekOut(**w.__dict__) for w in s.weeks],
            recent=[session_out(x) for x in training.recent_sessions(session, 5)],
            zone2="{}-{} bpm of HRmax {}".format(
                *analysis.zone2_bounds(analysis.hr_max(session)), analysis.hr_max(session)
            ),
            zone2_weeks=[Zone2Out(**z.__dict__) for z in analysis.zone2_weeks(session, weeks)],
        )


@mcp.tool(title="Exercise progress", annotations=READ)
def exercise_progress(
    exercise: Annotated[
        str, Field(min_length=2, description="Exercise name or part of it, e.g. 'Latzug'")
    ],
    weeks: Annotated[int, Field(ge=1, le=260, description="How many weeks back")] = 26,
) -> ExerciseProgressOut:
    """Progression of one exercise per session: top weight, estimated 1RM, reps and volume."""
    with session_scope() as session:
        try:
            found = training.find_exercise(session, exercise)
        except training.TrainingError as exc:
            raise ToolError(str(exc)) from exc
        points = training.progress(session, found, local_today() - timedelta(weeks=weeks))
        return ExerciseProgressOut(
            exercise=found.name,
            bodyweight=found.bodyweight,
            sessions=[
                ProgressOut(
                    date=p.date,
                    workout=p.workout_name,
                    sets=p.sets,
                    top_weight_kg=p.top_weight,
                    best_e1rm_kg=p.best_e1rm,
                    max_reps=p.max_reps,
                    volume_kg=p.volume_kg,
                )
                for p in points
            ],
        )


@mcp.tool(title="Progression suggestions", annotations=READ)
def progression_suggestions(
    weeks: Annotated[int, Field(ge=1, le=52, description="Exercises trained in this window")] = 8,
) -> ProgressionOut:
    """Next target per exercise by double progression (weight and reps), and the exercises that
    stagnate. Based on the working sets (top weight) of each exercise's last session."""
    with session_scope() as session:
        found = progression.suggestions(session, weeks)
        return ProgressionOut(
            rule=(
                "Double progression: when every working set reached the top of the rep range "
                "with at most 2 reps in reserve, add the weight step and go back to the bottom "
                "of the range; otherwise one more rep at the same weight."
            ),
            suggestions=[target_out(s) for s in found],
            stagnant=[target_out(s) for s in found if s.stagnant],
        )
