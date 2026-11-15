from datetime import date

from pydantic import BaseModel, Field


class CorrelationPoint(BaseModel):
    date: date
    x: float
    y: float = Field(description="Read `lag` days after the date")


class CorrelationRead(BaseModel):
    x: str
    y: str
    lag: int = Field(description="Days between x and y")
    n: int = Field(description="Days with both values")
    r: float | None = Field(description="Pearson's r, None below 10 days")
    points: list[CorrelationPoint]
