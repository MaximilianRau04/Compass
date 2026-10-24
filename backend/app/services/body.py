"""Body weight and waist: entering them, the 7-day mean and the weekly trend.

The weight of a day is one value (manual, else Health Connect, else the MFP export; see
app.services.nutrition.weights). The trend compares the mean of the last 7 days with the mean of
the 7 days before; single days swing with water and food, the means do not. The goal is a loss of
weight_loss_min..weight_loss_max kg per week (goals, default 0.2 to 0.4).
"""

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from statistics import mean

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.nutrition import BodyMeasurement, BodyWeight
from app.services import nutrition
from app.services.clock import local_today

WAIST = "waist_cm"
DEFAULT_LOSS = (0.2, 0.4)
# A 7-day mean needs a few weigh-ins to mean anything.
MIN_DAYS = 3


class BodyError(ValueError):
    pass


def log(session: Session, metric: str, value: float, day: date | None = None) -> date:
    """Store a weight (kg) or waist (cm) for a day; entering it again the same day replaces it."""
    day = day or local_today()
    if day > local_today():
        raise BodyError("the day is in the future")
    if metric == "weight":
        if not 20 <= value <= 400:
            raise BodyError("weight must be between 20 and 400 kg")
        row = session.scalar(
            select(BodyWeight).where(
                BodyWeight.source == nutrition.MANUAL, BodyWeight.local_date == day
            )
        )
        if row is None:
            row = BodyWeight(source=nutrition.MANUAL, local_date=day, kg=Decimal(0))
            session.add(row)
        row.kg = Decimal(str(value)).quantize(Decimal("0.01"))
    elif metric == "waist":
        if not 40 <= value <= 250:
            raise BodyError("waist must be between 40 and 250 cm")
        row = session.scalar(
            select(BodyMeasurement).where(
                BodyMeasurement.metric == WAIST, BodyMeasurement.local_date == day
            )
        )
        if row is None:
            row = BodyMeasurement(metric=WAIST, local_date=day, value=Decimal(0))
            session.add(row)
        row.value = Decimal(str(value)).quantize(Decimal("0.1"))
    else:
        raise BodyError("metric must be weight or waist")
    session.flush()
    return day


@dataclass
class DayWeight:
    date: date
    kg: float | None  # weigh-in of the day, if any
    source: str | None
    mean7: float | None  # mean of this day and the 6 before, if enough weigh-ins


@dataclass
class Waist:
    date: date
    cm: float


@dataclass
class Trend:
    today: date
    days: list[DayWeight]
    mean7: float | None
    mean7_before: float | None
    change_kg: float | None  # this week's mean minus last week's
    change_pct: float | None
    loss_per_week: float | None  # positive = losing
    loss_min: float
    loss_max: float
    status: str | None  # on_target | too_slow | too_fast | gaining
    waist: list[Waist]
    waist_change: float | None  # latest minus the one about a week (or more) before
    weekly: list[tuple[date, float | None, float | None]]  # week start, mean kg, waist cm


def _mean(values: list[float]) -> float | None:
    return round(mean(values), 2) if len(values) >= MIN_DAYS else None


def loss_goal(session: Session, day: date) -> tuple[float, float]:
    goals = nutrition.goals_on(session, day)
    low = goals.get("weight_loss_min", DEFAULT_LOSS[0])
    high = goals.get("weight_loss_max", DEFAULT_LOSS[1])
    return low, max(high, low)


def mean_between(points: dict[date, float], first: date, last: date) -> float | None:
    return _mean([kg for d, kg in points.items() if first <= d <= last])


def trend(session: Session, weeks: int = 8, today: date | None = None) -> Trend:
    today = today or local_today()
    since = today - timedelta(weeks=weeks) - timedelta(days=13)
    found = nutrition.weights(session, since)
    points = {p.date: p.kg for p in found}
    sources = {p.date: p.source for p in found}
    first_day = today - timedelta(weeks=weeks) + timedelta(days=1)
    day_list = [first_day + timedelta(days=i) for i in range((today - first_day).days + 1)]
    days = [
        DayWeight(d, points.get(d), sources.get(d), mean_between(points, d - timedelta(days=6), d))
        for d in day_list
    ]

    now = mean_between(points, today - timedelta(days=6), today)
    before = mean_between(points, today - timedelta(days=13), today - timedelta(days=7))
    change = round(now - before, 2) if now is not None and before is not None else None
    low, high = loss_goal(session, today)
    loss = -change if change is not None else None
    status = None
    if loss is not None:
        status = (
            "gaining"
            if loss < 0
            else "too_slow"
            if loss < low
            else "too_fast"
            if loss > high
            else "on_target"
        )

    waist = [
        Waist(m.local_date, float(m.value))
        for m in session.scalars(
            select(BodyMeasurement)
            .where(BodyMeasurement.metric == WAIST, BodyMeasurement.local_date >= since)
            .order_by(BodyMeasurement.local_date)
        )
    ]
    waist_change = None
    if waist:
        latest = waist[-1]
        earlier = [w for w in waist if w.date <= latest.date - timedelta(days=6)]
        if earlier:
            waist_change = round(latest.cm - earlier[-1].cm, 1)

    weekly = []
    start = today - timedelta(days=today.weekday()) - timedelta(weeks=weeks - 1)
    for i in range(weeks):
        ws = start + timedelta(weeks=i)
        we = ws + timedelta(days=6)
        kg = [v for d, v in points.items() if ws <= d <= we]
        cm = [w.cm for w in waist if ws <= w.date <= we]
        weekly.append((ws, round(mean(kg), 2) if kg else None, cm[-1] if cm else None))

    return Trend(
        today=today,
        days=days,
        mean7=now,
        mean7_before=before,
        change_kg=change,
        change_pct=round(change / before * 100, 2) if change is not None and before else None,
        loss_per_week=round(loss, 2) if loss is not None else None,
        loss_min=low,
        loss_max=high,
        status=status,
        waist=waist,
        waist_change=waist_change,
        weekly=weekly,
    )
