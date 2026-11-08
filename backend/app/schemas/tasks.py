from datetime import date, datetime, time

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.tasks import TaskPriority, TaskSource, TaskStatus
from app.schemas.calendar import CalendarEventRead
from app.services.recurrence import validate_rrule

# Limits of the free text fields; a tag matches the column (ARRAY(String(60))).
MAX_TAG = 60
MAX_NOTES = 20_000


class AreaRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    slug: str
    name: str
    color: str
    sort_order: int
    archived: bool


class AreaCreate(BaseModel):
    slug: str = Field(min_length=1, max_length=40, pattern=r"^[a-z0-9-]+$")
    name: str = Field(min_length=1, max_length=80)
    color: str = "slate"
    sort_order: int = 0


class AreaUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    color: str | None = None
    sort_order: int | None = None
    archived: bool | None = None


class _TaskFields(BaseModel):
    @field_validator("recurrence", check_fields=False)
    @classmethod
    def _rrule(cls, value: str | None) -> str | None:
        if value is None or value == "":
            return None
        return validate_rrule(value)

    @field_validator("tags", check_fields=False)
    @classmethod
    def _tags(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        tags = list(dict.fromkeys(t.strip().lower().lstrip("#") for t in value if t.strip()))
        if too_long := [t for t in tags if len(t) > MAX_TAG]:
            raise ValueError(f"tag {too_long[0][:20]!r}... is longer than {MAX_TAG} characters")
        return tags


class TaskCreate(_TaskFields):
    title: str = Field(min_length=1, max_length=500)
    notes: str | None = Field(default=None, max_length=MAX_NOTES)
    area_id: int | None = None
    tags: list[str] = []
    priority: TaskPriority = TaskPriority.normal
    status: TaskStatus = TaskStatus.open
    due_date: date | None = None
    due_time: time | None = None
    scheduled_date: date | None = None
    recurrence: str | None = None
    source: TaskSource = TaskSource.manual
    external_id: str | None = None


class TaskUpdate(_TaskFields):
    """All fields optional; only fields that are sent are changed (null clears a field)."""

    title: str | None = Field(default=None, min_length=1, max_length=500)
    notes: str | None = Field(default=None, max_length=MAX_NOTES)
    area_id: int | None = None
    tags: list[str] | None = None
    priority: TaskPriority | None = None
    status: TaskStatus | None = None
    due_date: date | None = None
    due_time: time | None = None
    scheduled_date: date | None = None
    recurrence: str | None = None
    sort_order: int | None = None


class TaskRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    notes: str | None
    area_id: int | None
    area: AreaRead | None
    tags: list[str]
    priority: TaskPriority
    status: TaskStatus
    due_date: date | None
    due_time: time | None
    scheduled_date: date | None
    completed_at: datetime | None
    recurrence: str | None
    source: TaskSource
    external_id: str | None
    sort_order: int
    created_at: datetime
    updated_at: datetime


class TaskEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    type: str
    actor: str
    payload: dict
    created_at: datetime


class QuickAddRequest(BaseModel):
    text: str = Field(min_length=1, max_length=1000)


class QuickAddPreview(BaseModel):
    title: str
    due_date: date | None
    due_time: time | None
    scheduled_date: date | None
    priority: TaskPriority | None
    area: AreaRead | None
    tags: list[str]
    recurrence: str | None


class TodayOverview(BaseModel):
    today: date
    overdue: list[TaskRead]
    due_today: list[TaskRead]
    scheduled: list[TaskRead]
    upcoming: list[TaskRead]
    done_today: list[TaskRead]
    events: list[CalendarEventRead]
