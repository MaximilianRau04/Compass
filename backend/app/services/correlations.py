"""Relations between two daily values, e.g. sleep against mood the same day or training volume
against the resting heart rate the day after. Built on the rows of app.services.daily: a day
without a value is left out, never counted as zero. Pearson's r with the number of days it rests
on; below MIN_DAYS there is no r, since a handful of days shows nothing but chance."""

import math
from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.services import daily
from app.services.clock import local_today

MIN_DAYS = 10

# Name -> how to read it from a DayRow. Training values count only on days with a session.
METRICS = {
    "sleep": lambda r: r.asleep_minutes / 60 if r.asleep_minutes is not None else None,
    "deep": lambda r: r.deep_minutes,
    "steps": lambda r: r.steps,
    "resting_hr": lambda r: r.resting_hr,
    "volume": lambda r: r.volume_kg if r.training else None,
    "zone2": lambda r: r.zone2_minutes if r.training else None,
    "kcal": lambda r: r.kcal if not r.nutrition_flags else None,
    "protein": lambda r: r.protein_g if not r.nutrition_flags else None,
    "weight": lambda r: r.weight_kg,
    "tasks_done": lambda r: r.tasks_done,
    "mood": lambda r: r.mood,
    "energy": lambda r: r.energy,
}

# Pairs shown without asking: (x, y, lag), y is read `lag` days after x.
PRESETS = (
    ("sleep", "mood", 0),
    ("sleep", "energy", 0),
    ("sleep", "resting_hr", 0),
    ("volume", "resting_hr", 1),
    ("volume", "sleep", 1),
    ("steps", "sleep", 1),
    ("kcal", "weight", 1),
    ("protein", "energy", 0),
    ("sleep", "tasks_done", 0),
    ("energy", "tasks_done", 0),
)


class CorrelationError(ValueError):
    pass


@dataclass
class Correlation:
    x: str
    y: str
    lag: int
    n: int
    r: float | None
    points: list[tuple[date, float, float]]  # day of x, x, y


def pearson(xs: list[float], ys: list[float]) -> float | None:
    n = len(xs)
    if n < MIN_DAYS:
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys, strict=True))
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    if sxx == 0 or syy == 0:
        return None
    return round(sxy / math.sqrt(sxx * syy), 2)


def correlate(rows: list[daily.DayRow], x: str, y: str, lag: int = 0) -> Correlation:
    if x not in METRICS or y not in METRICS:
        raise CorrelationError(f"known values: {', '.join(METRICS)}")
    if not 0 <= lag <= 7:
        raise CorrelationError("lag goes from 0 to 7 days")
    by_day = {r.date: r for r in rows}
    points = []
    for r in rows:
        later = by_day.get(r.date + timedelta(days=lag))
        if later is None:
            continue
        vx, vy = METRICS[x](r), METRICS[y](later)
        if vx is not None and vy is not None:
            points.append((r.date, float(vx), float(vy)))
    r_value = pearson([p[1] for p in points], [p[2] for p in points])
    return Correlation(x=x, y=y, lag=lag, n=len(points), r=r_value, points=points)


def rows_for(session: Session, days: int, today: date | None = None) -> list[daily.DayRow]:
    # Today is still running: its sleep and food are not complete yet.
    until = (today or local_today()) - timedelta(days=1)
    return daily.daily_rows(session, days, until)


def overview(session: Session, days: int = 90) -> list[Correlation]:
    """The preset pairs, strongest first; pairs without enough days last."""
    rows = rows_for(session, days)
    found = [correlate(rows, x, y, lag) for x, y, lag in PRESETS]
    return sorted(found, key=lambda c: -abs(c.r) if c.r is not None else 1)
