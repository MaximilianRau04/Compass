"""Nutrition, body weight and goals, shared by the REST API, the MCP server and the ingestion.

Meals come from Health Connect (a nutrition app writes every meal there, ongoing) and from exports
of those apps (backfill of the past). For each day, Health Connect wins if it has meals that day;
otherwise the export rows are used. Days without any meal were not tracked and stay empty.
"""

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from statistics import mean

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models.health import HealthRecord
from app.models.nutrition import BodyWeight, Goal, NutritionMeal
from app.services.clock import local_today, utc_now

HEALTHCONNECT = "healthconnect"
# Preference when a day has both: the ongoing source wins over the backfill.
SOURCES = (HEALTHCONNECT, "mfp_export", "cronometer_export", "loseit_export")
MANUAL = "manual"
# A weight typed in Compass beats a synced one of the same day.
WEIGHT_SOURCES = (MANUAL, *SOURCES)
MEAL_ORDER = ("breakfast", "lunch", "dinner", "snack", "unknown")
MACROS = (
    "protein_g",
    "carbs_g",
    "fat_g",
    "saturated_fat_g",
    "fiber_g",
    "sugar_g",
    "sodium_mg",
    "potassium_mg",
    "calcium_mg",
    "iron_mg",
)
# A logged day below this is most likely not logged completely.
INCOMPLETE_KCAL = 1500
GOAL_METRICS = (
    "kcal",
    "protein_g",
    "carbs_g",
    "fat_g",
    "steps",
    "hr_max",
    "weight_loss_min",
    "weight_loss_max",
)
# Fields in a Health Connect nutrition record (see android/.../HealthTypes.kt) -> meal columns.
HC_FIELDS = {"kcal": "energy_kcal", **{m: m for m in MACROS}}


class NutritionError(ValueError):
    pass


def _dec(value) -> Decimal | None:
    return None if value is None else Decimal(str(value)).quantize(Decimal("0.1"))


# --- Health Connect -> meals and weight ---------------------------------------------------------


def rebuild_from_healthconnect(session: Session, days: set[date]) -> None:
    """Rebuild the Health Connect meals and weights of these days from the stored records.

    MFP may write one record per meal or per food; either way the meal is the sum. If several apps
    write nutrition for the same day, the app with the most calories that day is used (summing two
    apps would count the same food twice)."""
    if not days:
        return
    records = list(
        session.scalars(
            select(HealthRecord).where(
                HealthRecord.type.in_(("nutrition", "weight")),
                HealthRecord.deleted_at.is_(None),
                HealthRecord.local_date.in_(days),
            )
        )
    )

    # day -> app -> meal -> field -> total
    meals: dict[date, dict[str, dict[str, dict[str, float]]]] = defaultdict(
        lambda: defaultdict(lambda: defaultdict(lambda: defaultdict(float)))
    )
    present: dict[tuple[date, str, str], set[str]] = defaultdict(set)
    latest_weight: dict[date, HealthRecord] = {}
    for r in records:
        data = r.raw.get("data") or {}
        if r.type == "weight":
            # The earliest weigh-in of the day: the morning weight, comparable day to day.
            current = latest_weight.get(r.local_date)
            if data.get("kg") is not None and (current is None or r.start_at < current.start_at):
                latest_weight[r.local_date] = r
            continue
        meal = data.get("meal_type") if data.get("meal_type") in MEAL_ORDER else "unknown"
        for column, key in HC_FIELDS.items():
            value = data.get(key)
            if isinstance(value, int | float):
                meals[r.local_date][r.source_app][meal][column] += value
                present[(r.local_date, r.source_app, meal)].add(column)

    session.execute(
        delete(NutritionMeal).where(
            NutritionMeal.source == HEALTHCONNECT, NutritionMeal.local_date.in_(days)
        )
    )
    for day, apps in meals.items():
        app, per_meal = max(
            apps.items(), key=lambda item: sum(m.get("kcal", 0) for m in item[1].values())
        )
        for meal, totals in per_meal.items():
            known = present[(day, app, meal)]
            session.add(
                NutritionMeal(
                    source=HEALTHCONNECT,
                    local_date=day,
                    meal=meal,
                    kcal=_dec(totals.get("kcal", 0)),
                    **{m: _dec(totals[m]) if m in known else None for m in MACROS},
                    raw={"app": app},
                )
            )

    session.execute(
        delete(BodyWeight).where(
            BodyWeight.source == HEALTHCONNECT, BodyWeight.local_date.in_(days)
        )
    )
    for day, r in latest_weight.items():
        session.add(
            BodyWeight(
                source=HEALTHCONNECT,
                local_date=day,
                kg=Decimal(str(r.raw["data"]["kg"])).quantize(Decimal("0.01")),
                measured_at=r.start_at,
            )
        )
    session.flush()


# --- Reading -----------------------------------------------------------------------------------


@dataclass
class Meal:
    meal: str
    kcal: float
    protein_g: float | None
    carbs_g: float | None
    fat_g: float | None


@dataclass
class Day:
    date: date
    source: str
    kcal: float
    protein_g: float | None
    carbs_g: float | None
    fat_g: float | None
    fiber_g: float | None
    sugar_g: float | None
    sodium_mg: float | None
    saturated_fat_g: float | None = None
    potassium_mg: float | None = None
    calcium_mg: float | None = None
    iron_mg: float | None = None
    meals: list[Meal] = field(default_factory=list)
    # Data quality, see summary(): "incomplete" (under INCOMPLETE_KCAL), "same_as_previous_day".
    flags: list[str] = field(default_factory=list)


def _total(rows: list[NutritionMeal], column: str) -> float | None:
    values = [getattr(r, column) for r in rows if getattr(r, column) is not None]
    return round(float(sum(values)), 1) if values else None


def days(session: Session, since: date, until: date) -> list[Day]:
    """Tracked days in the range, oldest first, each from its preferred source."""
    by_day: dict[date, dict[str, list[NutritionMeal]]] = defaultdict(lambda: defaultdict(list))
    for m in session.scalars(
        select(NutritionMeal).where(
            NutritionMeal.local_date >= since, NutritionMeal.local_date <= until
        )
    ):
        by_day[m.local_date][m.source].append(m)
    out = []
    for day in sorted(by_day):
        source = next(s for s in (*SOURCES, *by_day[day]) if s in by_day[day])
        rows = sorted(by_day[day][source], key=lambda m: MEAL_ORDER.index(m.meal))
        out.append(
            Day(
                date=day,
                source=source,
                kcal=_total(rows, "kcal") or 0.0,
                protein_g=_total(rows, "protein_g"),
                carbs_g=_total(rows, "carbs_g"),
                fat_g=_total(rows, "fat_g"),
                fiber_g=_total(rows, "fiber_g"),
                sugar_g=_total(rows, "sugar_g"),
                sodium_mg=_total(rows, "sodium_mg"),
                saturated_fat_g=_total(rows, "saturated_fat_g"),
                potassium_mg=_total(rows, "potassium_mg"),
                calcium_mg=_total(rows, "calcium_mg"),
                iron_mg=_total(rows, "iron_mg"),
                meals=[
                    Meal(
                        meal=m.meal,
                        kcal=float(m.kcal),
                        protein_g=float(m.protein_g) if m.protein_g is not None else None,
                        carbs_g=float(m.carbs_g) if m.carbs_g is not None else None,
                        fat_g=float(m.fat_g) if m.fat_g is not None else None,
                    )
                    for m in rows
                ],
            )
        )
    return out


@dataclass
class WeightPoint:
    date: date
    kg: float
    source: str


def weights(session: Session, since: date | None = None) -> list[WeightPoint]:
    """One weight per day, oldest first: manual, else Health Connect, else the export."""
    stmt = select(BodyWeight).order_by(BodyWeight.local_date)
    if since is not None:
        stmt = stmt.where(BodyWeight.local_date >= since)
    best: dict[date, BodyWeight] = {}
    for w in session.scalars(stmt):
        current = best.get(w.local_date)
        if current is None or WEIGHT_SOURCES.index(w.source) < WEIGHT_SOURCES.index(current.source):
            best[w.local_date] = w
    return [WeightPoint(d, float(w.kg), w.source) for d, w in sorted(best.items())]


# --- Goals -------------------------------------------------------------------------------------


def goals_on(session: Session, day: date) -> dict[str, float]:
    """The goal of each metric valid on a day."""
    out: dict[str, float] = {}
    for g in session.scalars(
        select(Goal).where(Goal.valid_from <= day).order_by(Goal.metric, Goal.valid_from)
    ):
        out[g.metric] = float(g.value)
    return out


def set_goal(session: Session, metric: str, value: float, valid_from: date | None = None) -> Goal:
    if metric not in GOAL_METRICS:
        raise NutritionError(f"unknown goal {metric!r}, use one of {', '.join(GOAL_METRICS)}")
    if value <= 0:
        raise NutritionError("a goal must be greater than 0")
    valid_from = valid_from or local_today()
    goal = session.scalar(select(Goal).where(Goal.metric == metric, Goal.valid_from == valid_from))
    if goal is None:
        goal = Goal(metric=metric, valid_from=valid_from, created_at=utc_now())
        session.add(goal)
    goal.value = _dec(value)
    session.flush()
    return goal


# --- Summary -----------------------------------------------------------------------------------


@dataclass
class Week:
    week_start: date
    days_tracked: int
    kcal: float
    protein_g: float | None


# Averaged per day in the summary.
AVERAGED = (
    "kcal",
    "protein_g",
    "carbs_g",
    "fat_g",
    "fiber_g",
    "sugar_g",
    "sodium_mg",
    "saturated_fat_g",
    "potassium_mg",
    "calcium_mg",
    "iron_mg",
)


@dataclass
class Quality:
    incomplete: list[date]  # logged, but under INCOMPLETE_KCAL
    same_as_previous_day: list[date]  # the same totals as the day before (copied or not logged)
    gaps: list[date]  # not logged at all
    valid_days: int  # complete days that count for the averages


@dataclass
class Summary:
    since: date
    until: date
    days: list[Day]
    goals: dict[str, float]
    averages: dict[str, float | None]  # over valid days only
    averages_all: dict[str, float | None]  # over every complete logged day, flagged ones too
    quality: Quality
    weeks: list[Week]
    protein_goal_days: int | None
    weight: WeightPoint | None
    weight_change: float | None


def _avg(values: list[float | None]) -> float | None:
    present = [v for v in values if v is not None]
    return round(mean(present), 1) if present else None


def _same_totals(a: Day, b: Day) -> bool:
    return (a.kcal, a.protein_g, a.carbs_g, a.fat_g) == (b.kcal, b.protein_g, b.carbs_g, b.fat_g)


def flag_days(tracked: list[Day], until: date) -> None:
    """Mark days that probably do not show what was eaten. Today is still running: never flagged."""
    by_date = {d.date: d for d in tracked}
    for d in tracked:
        if d.date >= until:
            continue
        if d.kcal < INCOMPLETE_KCAL:
            d.flags.append("incomplete")
        previous = by_date.get(d.date - timedelta(days=1))
        if previous is not None and d.kcal > 0 and _same_totals(d, previous):
            d.flags.append("same_as_previous_day")


def summary(session: Session, n_days: int) -> Summary:
    until = local_today()
    since = until - timedelta(days=n_days - 1)
    # One day more, so the first day can be compared with the one before.
    tracked = days(session, since - timedelta(days=1), until)
    flag_days(tracked, until)
    tracked = [d for d in tracked if d.date >= since]
    goals = goals_on(session, until)
    # Today is still running; averages and goal counts only use complete days, and of those
    # only the ones without a quality flag.
    complete = [d for d in tracked if d.date < until] or tracked
    valid = [d for d in complete if not d.flags]
    logged = {d.date for d in tracked}
    quality = Quality(
        incomplete=[d.date for d in complete if "incomplete" in d.flags],
        same_as_previous_day=[d.date for d in complete if "same_as_previous_day" in d.flags],
        gaps=[
            since + timedelta(days=i)
            for i in range((until - since).days)
            if since + timedelta(days=i) not in logged
        ],
        valid_days=len(valid),
    )

    weeks: dict[date, list[Day]] = defaultdict(list)
    for d in tracked:
        weeks[d.date - timedelta(days=d.date.weekday())].append(d)

    # Counted against the goal that was valid on each day, not today's.
    protein_goal_days = None
    if "protein_g" in goals:
        protein_goal_days = 0
        for d in valid:
            goal = goals_on(session, d.date).get("protein_g")
            if goal is not None and d.protein_g is not None and d.protein_g >= goal:
                protein_goal_days += 1

    in_range = weights(session, since)
    latest = weights(session)[-1:] if not in_range else in_range[-1:]
    return Summary(
        since=since,
        until=until,
        days=tracked,
        goals=goals,
        averages={k: _avg([getattr(d, k) for d in valid]) for k in AVERAGED},
        averages_all={k: _avg([getattr(d, k) for d in complete]) for k in AVERAGED},
        quality=quality,
        weeks=[
            Week(
                week_start=start,
                days_tracked=len(ds),
                kcal=round(mean(d.kcal for d in ds)),
                protein_g=_avg([d.protein_g for d in ds]),
            )
            for start, ds in sorted(weeks.items())
        ],
        protein_goal_days=protein_goal_days,
        weight=latest[0] if latest else None,
        weight_change=round(in_range[-1].kg - in_range[0].kg, 1) if len(in_range) > 1 else None,
    )
