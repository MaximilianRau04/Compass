from datetime import date, datetime

from pydantic import BaseModel, Field


class SessionBrief(BaseModel):
    id: int
    started_at: datetime
    workout_name: str
    split: str
    exercises: int
    sets: int
    volume_kg: float
    duration_minutes: int | None
    source: str = Field(
        description="gymday (CSV with sets), healthconnect (Gym Day session only) or watch "
        "(another app's workout, e.g. bouldering)"
    )
    activity: str | None = Field(
        None, description="Health Connect exercise type of a watch workout"
    )
    hr_avg: int | None = Field(None, description="Average heart rate from the watch")
    hr_max: int | None = None


class WeekRead(BaseModel):
    week_start: date
    sessions: int
    sets: int
    volume_kg: float


class TrainingSummaryRead(BaseModel):
    since: date
    sessions: int
    sets: int
    volume_kg: float
    this_week_sessions: int
    last_session: SessionBrief | None
    weeks: list[WeekRead]
    split: dict[str, int]


class SetRead(BaseModel):
    set_index: int
    weight_kg: float | None = Field(description="None for bodyweight sets")
    reps: int | None
    rir: int | None = None
    e1rm: float | None


class SessionExercise(BaseModel):
    exercise_id: int
    name: str
    bodyweight: bool
    sets: list[SetRead]


class SessionDetail(SessionBrief):
    exercise_sets: list[SessionExercise]


class ExerciseRead(BaseModel):
    id: int
    name: str
    muscle_group: str | None
    bodyweight: bool
    rep_min: int = Field(description="Bottom of the rep range (default 8)")
    rep_max: int = Field(description="Top of the rep range (default 12)")
    weight_step: float = Field(description="kg added once the top of the range is reached")
    aliases: list[str]
    sessions: int
    sets: int
    last_at: datetime | None
    best_e1rm: float | None
    best_weight: float | None
    max_reps: int | None


class ExerciseUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    muscle_group: str | None = Field(default=None, max_length=60)
    bodyweight: bool | None = None
    rep_min: int | None = Field(default=None, ge=1, le=100)
    rep_max: int | None = Field(default=None, ge=1, le=100)
    weight_step: float | None = Field(default=None, gt=0, le=50)


class DoneSetRead(BaseModel):
    weight_kg: float | None
    reps: int | None
    rir: int | None


class SuggestionRead(BaseModel):
    exercise_id: int
    name: str
    bodyweight: bool
    last_date: date
    last_sets: list[DoneSetRead] = Field(description="Working sets of the last session")
    last_set_count: int = Field(description="All sets of the last session")
    rep_min: int
    rep_max: int
    weight_step: float
    action: str = Field(
        description="increase: more weight at rep_min; reps: same weight, more reps"
    )
    weight_kg: float | None = Field(description="Target weight; extra load for bodyweight")
    reps: int = Field(description="Target reps per working set")
    rir_known: bool = Field(description="False when the last sets had no RIR logged")
    same_sessions: int = Field(description="Sessions in a row with the same working sets")
    stagnant: bool


class ProgressionRead(BaseModel):
    suggestions: list[SuggestionRead]
    stagnant: list[SuggestionRead]


class WorkoutNameRead(BaseModel):
    name: str
    last_at: datetime


class TemplateExercise(BaseModel):
    exercise_id: int
    name: str
    bodyweight: bool
    suggestion: SuggestionRead | None


class TemplateRead(BaseModel):
    workout_name: str
    exercises: list[TemplateExercise]


class MergeRequest(BaseModel):
    into: int = Field(description="Id of the exercise that keeps the sets")


class ProgressPointRead(BaseModel):
    date: date
    session_id: int
    workout_name: str
    sets: int
    top_weight: float | None
    best_e1rm: float | None
    max_reps: int | None
    volume_kg: float


class ImportResult(BaseModel):
    rows: int
    sessions_created: int
    sets_created: int
    sets_updated: int
    sets_unchanged: int
    exercises_created: int
    first: date
    last: date
