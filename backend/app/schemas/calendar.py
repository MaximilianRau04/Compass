from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class CalendarEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    feed: str
    title: str
    location: str | None
    starts_at: datetime
    ends_at: datetime | None
    all_day: bool
    area: str | None = Field(
        None, validation_alias="area_slug", description="Area slug of its calendar, if set"
    )


class IntegrationStateRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str
    last_run_at: datetime | None
    last_success_at: datetime | None
    last_error: str | None
    stats: dict
