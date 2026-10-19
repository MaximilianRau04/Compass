from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.tasks import AreaRead

MAX_BODY = 100_000


def clean_tags(value: list[str] | None) -> list[str] | None:
    if value is None:
        return None
    return list(dict.fromkeys(t.strip().lower().lstrip("#") for t in value if t.strip()))[:30]


class _NoteFields(BaseModel):
    @field_validator("tags", check_fields=False)
    @classmethod
    def _tags(cls, value: list[str] | None) -> list[str] | None:
        return clean_tags(value)


class NoteCreate(_NoteFields):
    title: str = Field(min_length=1, max_length=300)
    body: str = Field("", max_length=MAX_BODY)
    area_id: int | None = None
    tags: list[str] = []
    pinned: bool = False
    task_id: int | None = None
    source: str = Field("manual", pattern="^(manual|share)$")


class NoteUpdate(_NoteFields):
    title: str | None = Field(None, min_length=1, max_length=300)
    body: str | None = Field(None, max_length=MAX_BODY)
    area_id: int | None = None
    tags: list[str] | None = None
    pinned: bool | None = None
    archived: bool | None = None
    task_id: int | None = None


class QuickNote(BaseModel):
    text: str = Field(min_length=1, max_length=MAX_BODY)


class NoteRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    body: str
    area_id: int | None
    area: AreaRead | None
    tags: list[str]
    pinned: bool
    archived: bool
    source: str
    task_id: int | None
    created_at: datetime
    updated_at: datetime


class NoteListItem(BaseModel):
    id: int
    title: str
    snippet: str = Field(description="Start of the note, or the part around a search hit")
    area: AreaRead | None
    tags: list[str]
    pinned: bool
    archived: bool
    source: str
    task_id: int | None
    updated_at: datetime


class TagCount(BaseModel):
    tag: str
    count: int
