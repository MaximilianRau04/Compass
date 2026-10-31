from datetime import date
from typing import Literal

from pydantic import BaseModel, Field


class BodyLog(BaseModel):
    metric: Literal["weight", "waist"]
    value: float = Field(description="kg for weight, cm for waist")
    day: date | None = Field(None, description="Default today")


class DayWeightRead(BaseModel):
    date: date
    kg: float | None
    source: str | None
    mean7: float | None


class WaistRead(BaseModel):
    date: date
    cm: float


class WeekBodyRead(BaseModel):
    week_start: date
    kg: float | None = Field(description="Mean weight of the week")
    waist_cm: float | None


class BodyTrendRead(BaseModel):
    today: date
    days: list[DayWeightRead]
    mean7: float | None = Field(description="Mean of the last 7 days (at least 3 weigh-ins)")
    mean7_before: float | None
    change_kg: float | None = Field(description="Week over week, negative = losing")
    change_pct: float | None
    loss_per_week: float | None
    loss_min: float
    loss_max: float
    status: str | None = Field(
        description="on_target, too_slow, too_fast or gaining; only with a weight loss goal"
    )
    waist: list[WaistRead]
    waist_change: float | None
    weeks: list[WeekBodyRead]
