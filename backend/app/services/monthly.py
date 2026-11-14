"""The monthly review: a calendar month in numbers against the month before, across sleep,
training, nutrition, body, tasks, the journal and money. Unlike the weekly review it gives no
recommendation, it only reports. The worker saves it on the 1st as the brief of kind "monthly"."""

from dataclasses import dataclass, field
from datetime import date, timedelta
from statistics import mean, median

from sqlalchemy.orm import Session

from app.i18n import number, t
from app.services import briefs, daily, finance
from app.services.clock import local_today
from app.services.review import _best_e1rm, _hours, _num


@dataclass
class MonthNumbers:
    days: int
    sleep_avg_minutes: int | None = None
    nights: int = 0
    resting_hr: float | None = None
    steps_median: int | None = None
    sessions: int = 0
    volume_kg: float = 0.0
    kcal: int | None = None
    protein_g: int | None = None
    nutrition_days: int = 0
    weight_first: float | None = None
    weight_last: float | None = None
    tasks_done: int = 0
    mood: float | None = None
    energy: float | None = None
    journal_days: int = 0


@dataclass
class MonthlyReview:
    month: str  # YYYY-MM
    since: date
    until: date
    now: MonthNumbers
    before: MonthNumbers
    strength_up: list[tuple[str, float]] = field(default_factory=list)  # exercise, % change
    income: float | None = None
    spending: float | None = None
    saved: float | None = None
    top_categories: list[tuple[str, float]] = field(default_factory=list)


def month_bounds(day: date) -> tuple[date, date]:
    first = day.replace(day=1)
    nxt = (first + timedelta(days=32)).replace(day=1)
    return first, nxt - timedelta(days=1)


def _avg(values: list[float]) -> float | None:
    return round(mean(values), 1) if values else None


def numbers(session: Session, first: date, last: date) -> MonthNumbers:
    rows = daily.daily_rows(session, (last - first).days + 1, last)
    sleep = [r.asleep_minutes for r in rows if r.asleep_minutes is not None]
    resting = [r.resting_hr for r in rows if r.resting_hr is not None]
    steps = [r.steps for r in rows if r.steps is not None]
    food = [r for r in rows if r.kcal is not None and not r.nutrition_flags]
    weights = [r.weight_kg for r in rows if r.weight_kg is not None]
    moods = [r.mood for r in rows if r.mood is not None]
    energies = [r.energy for r in rows if r.energy is not None]
    return MonthNumbers(
        days=len(rows),
        sleep_avg_minutes=round(mean(sleep)) if sleep else None,
        nights=len(sleep),
        resting_hr=_avg(resting),
        steps_median=round(median(steps)) if steps else None,
        sessions=sum(len(r.training) for r in rows),
        volume_kg=round(sum(r.volume_kg for r in rows)),
        kcal=round(mean(r.kcal for r in food)) if food else None,
        protein_g=round(mean(r.protein_g or 0 for r in food)) if food else None,
        nutrition_days=len(food),
        weight_first=weights[0] if weights else None,
        weight_last=weights[-1] if weights else None,
        tasks_done=sum(r.tasks_done for r in rows),
        mood=_avg(moods),
        energy=_avg(energies),
        journal_days=len({r.date for r in rows if r.mood is not None or r.energy is not None}),
    )


def monthly_review(session: Session, today: date | None = None) -> MonthlyReview:
    """The last full month before `today`."""
    today = today or local_today()
    since, until = month_bounds(today.replace(day=1) - timedelta(days=1))
    prev_since, prev_until = month_bounds(since - timedelta(days=1))
    out = MonthlyReview(
        month=f"{since:%Y-%m}",
        since=since,
        until=until,
        now=numbers(session, since, until),
        before=numbers(session, prev_since, prev_until),
    )
    best_now = _best_e1rm(session, since, until)
    best_before = _best_e1rm(session, prev_since, prev_until)
    changes = [
        (name, round((value / best_before[name] - 1) * 100, 1))
        for name, value in best_now.items()
        if best_before.get(name)
    ]
    out.strength_up = sorted((c for c in changes if c[1] > 0), key=lambda c: -c[1])[:3]
    for m in finance.months(session, 1, until):
        if m.income or m.spending or m.saved:
            out.income, out.spending, out.saved = m.income, m.spending, m.saved
            out.top_categories = list(m.by_category.items())[:3]
    return out


def _vs(now: float | None, before: float | None, unit: str = "", digits: int = 0) -> str:
    """The value of this month with the one of the month before in brackets."""
    text = _num(now, unit, digits)
    if now is not None and before is not None:
        text += t("monthly.before", value=_num(before, unit, digits))
    return text


def markdown(r: MonthlyReview) -> str:
    n, b = r.now, r.before
    sleep = _hours(n.sleep_avg_minutes)
    if b.sleep_avg_minutes is not None and n.sleep_avg_minutes is not None:
        sleep += t("monthly.before", value=_hours(b.sleep_avg_minutes))
    lines = [
        t("review.sleep"),
        t("monthly.sleep", avg=sleep, n=n.nights),
        t("monthly.resting", bpm=_vs(n.resting_hr, b.resting_hr, "bpm", 1)),
        t("monthly.steps", n=_vs(n.steps_median, b.steps_median)),
        "",
        t("review.training"),
        t(
            "monthly.sessions",
            n=_vs(n.sessions, b.sessions),
            kg=_vs(n.volume_kg, b.volume_kg, "kg"),
        ),
    ]
    if r.strength_up:
        names = ", ".join(f"{name} +{number(pct, 1)} %" for name, pct in r.strength_up)
        lines.append(t("monthly.strength", names=names))
    lines += [
        "",
        t("review.nutrition"),
        t(
            "monthly.food",
            kcal=_vs(n.kcal, b.kcal, "kcal"),
            protein=_num(n.protein_g, "g"),
            days=n.nutrition_days,
        ),
    ]
    if n.weight_first is not None and n.weight_last is not None:
        first, last = _num(n.weight_first, "kg", 1), _num(n.weight_last, "kg", 1)
        lines.append(t("monthly.weight", first=first, last=last))
    lines += ["", t("monthly.days"), t("monthly.tasks", n=_vs(n.tasks_done, b.tasks_done))]
    if n.journal_days:
        lines.append(
            t(
                "monthly.journal",
                mood=_vs(n.mood, b.mood, digits=1),
                energy=_vs(n.energy, b.energy, digits=1),
                n=n.journal_days,
            )
        )
    if r.spending is not None:
        lines += [
            "",
            t("monthly.money"),
            t(
                "monthly.cash",
                income=_num(r.income),
                spending=_num(r.spending),
                saved=_num(r.saved),
            ),
        ]
        if r.top_categories:
            top = ", ".join(f"{cat} {number(v)}" for cat, v in r.top_categories)
            lines.append(t("monthly.top", top=top))
    return "\n".join(lines)


def save_monthly(session: Session, today: date | None = None) -> MonthlyReview:
    """Store last month's review as the brief of kind "monthly" (run by the worker on the 1st)."""
    review = monthly_review(session, today)
    briefs.save(
        session,
        "monthly",
        markdown(review),
        title=t("monthly.title", month=review.month),
        day=today or local_today(),
        actor="worker",
    )
    return review
