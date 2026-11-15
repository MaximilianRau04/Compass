from datetime import date

from pydantic import BaseModel, ConfigDict, Field


class ReadinessRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    date: date
    score: int | None = Field(description="0 to 100, null without last night or a resting HR")
    level: str | None = Field(description="good, moderate or low")
    reasons: list[str] = Field(description="short_sleep, resting_up, hrv_down, high_load")
    asleep_minutes: int | None
    resting_hr: int | None
    resting_median: float | None
    hrv: float | None
    hrv_median: float | None
