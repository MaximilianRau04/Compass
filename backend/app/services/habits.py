"""Habits: something to do every day, ticked by hand or by Compass from the day's data.

Rules: steps_goal (steps at least the goal "steps"), protein_goal (logged protein at least the
goal "protein_g"), sleep_need (asleep at least SLEEP_NEED_MINUTES the night before), journal (a
journal entry for the day). A rule without its goal is never met. The streak counts the days in a
row up to today; today only adds once done, so an open today does not break it."""

from dataclasses import dataclass, field
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.habits import Habit, HabitCheck
from app.models.journal import JournalEntry
from app.models.nutrition import Goal
from app.services import daily
from app.services.clock import local_today

RULES = ("steps_goal", "protein_goal", "sleep_need", "journal")
# Days looked back for the streak and the history.
WINDOW = 60


class HabitError(ValueError):
    pass


@dataclass
class HabitStatus:
    habit: Habit
    done_today: bool
    streak: int
    # Oldest first, the last WINDOW days including today.
    days: list[bool] = field(default_factory=list)


GOAL_RULES = {"steps_goal": "steps", "protein_goal": "protein_g"}


def _goals_by_day(session: Session, days: list[date]) -> dict[date, dict[str, float]]:
    """The goals valid on each day, read in one query (like nutrition.goals_on per day)."""
    rows = list(
        session.scalars(
            select(Goal)
            .where(Goal.metric.in_(GOAL_RULES.values()), Goal.valid_from <= max(days))
            .order_by(Goal.valid_from)
        )
    )
    out, current, i = {}, {}, 0
    for day in sorted(days):
        while i < len(rows) and rows[i].valid_from <= day:
            current[rows[i].metric] = float(rows[i].value)
            i += 1
        out[day] = dict(current)
    return out


def _rule_met(
    rule: str, row: daily.DayRow, goals: dict[str, float], journal_days: set[date]
) -> bool:
    if rule == "steps_goal":
        return "steps" in goals and row.steps is not None and row.steps >= goals["steps"]
    if rule == "protein_goal":
        return (
            "protein_g" in goals
            and row.protein_g is not None
            and row.protein_g >= goals["protein_g"]
        )
    if rule == "sleep_need":
        need = get_settings().sleep_need_minutes
        return row.asleep_minutes is not None and row.asleep_minutes >= need
    if rule == "journal":
        # An entry exists only with mood, energy or text (see app.services.journal).
        return row.date in journal_days
    return False


def active(session: Session) -> list[Habit]:
    return list(
        session.scalars(
            select(Habit).where(Habit.archived.is_(False)).order_by(Habit.sort_order, Habit.id)
        )
    )


def create(session: Session, name: str, rule: str | None = None) -> Habit:
    name = " ".join(name.split())
    if not name:
        raise HabitError("a habit needs a name")
    if rule is not None and rule not in RULES:
        raise HabitError(f"unknown rule {rule!r}, use one of {', '.join(RULES)}")
    habit = Habit(name=name[:120], rule=rule, sort_order=len(active(session)), archived=False)
    session.add(habit)
    session.flush()
    return habit


def archive(session: Session, habit: Habit) -> None:
    habit.archived = True
    session.flush()


def check(session: Session, habit: Habit, day: date, done: bool) -> None:
    """Tick or untick a manual habit; a habit with a rule follows its data."""
    if habit.rule is not None:
        raise HabitError("this habit is ticked from the data")
    if day > local_today():
        raise HabitError("the day lies in the future")
    existing = session.get(HabitCheck, (habit.id, day))
    if done and existing is None:
        session.add(HabitCheck(habit_id=habit.id, local_date=day))
    elif not done and existing is not None:
        session.delete(existing)
    session.flush()


def statuses(session: Session, today: date | None = None) -> list[HabitStatus]:
    today = today or local_today()
    since = today - timedelta(days=WINDOW - 1)
    habits = active(session)
    if not habits:
        return []
    rows = daily.daily_rows(session, WINDOW, today) if any(h.rule for h in habits) else []
    checks = {
        (c.habit_id, c.local_date)
        for c in session.scalars(select(HabitCheck).where(HabitCheck.local_date >= since))
    }
    journal_days = set(
        session.scalars(
            select(JournalEntry.local_date).where(
                JournalEntry.local_date >= since, JournalEntry.local_date <= today
            )
        )
    )
    goals = (
        _goals_by_day(session, [r.date for r in rows])
        if any(h.rule in GOAL_RULES for h in habits)
        else {}
    )
    out = []
    for h in habits:
        if h.rule:
            days = [_rule_met(h.rule, r, goals.get(r.date, {}), journal_days) for r in rows]
        else:
            days = [(h.id, since + timedelta(days=i)) in checks for i in range(WINDOW)]
        streak = 0
        for done in reversed(days[:-1]):
            if not done:
                break
            streak += 1
        if days[-1]:
            streak += 1
        out.append(HabitStatus(habit=h, done_today=days[-1], streak=streak, days=days))
    return out
