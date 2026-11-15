from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from app.services.journal import MAX_TEXT


class JournalRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    local_date: date
    mood: int | None
    energy: int | None
    text: str
    updated_at: datetime | None = None


class JournalWrite(BaseModel):
    mood: int | None = Field(None, ge=1, le=5)
    energy: int | None = Field(None, ge=1, le=5)
    text: str | None = Field(None, max_length=MAX_TEXT)


class JournalBrief(BaseModel):
    kind: str
    title: str | None
    body: str


class JournalDayRead(BaseModel):
    date: date
    entry: JournalRead | None
    briefs: list[JournalBrief]
    tasks_done: list[str]
    training: list[str]
    asleep_minutes: int | None
    steps: int | None
    resting_hr: int | None
    kcal: int | None
    protein_g: int | None
    weight_kg: float | None
