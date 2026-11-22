"""Tools for daily habits: status, streaks and ticking manual habits."""

from datetime import date
from typing import Annotated

from mcp.server.mcpserver.exceptions import ToolError
from pydantic import BaseModel, Field

from app.mcp.core import READ, WRITE, mcp
from app.mcp.db import session_scope
from app.mcp.guards import audited
from app.models.habits import Habit
from app.services import habits
from app.services.clock import local_today


class HabitOut(BaseModel):
    id: int
    name: str
    rule: str | None = Field(description="None for manual habits; otherwise auto-checked from data")
    done_today: bool
    streak: int
    last_14_days: list[bool] = Field(description="Oldest first, ending today")


class HabitsOut(BaseModel):
    today: date
    habits: list[HabitOut]


def _out(s: habits.HabitStatus) -> HabitOut:
    return HabitOut(
        id=s.habit.id,
        name=s.habit.name,
        rule=s.habit.rule,
        done_today=s.done_today,
        streak=s.streak,
        last_14_days=s.days[-14:],
    )


@mcp.tool(title="Habits", annotations=READ)
def list_habits() -> HabitsOut:
    """Active daily habits with today's status, current streak and the last 14 days."""
    with session_scope() as session:
        today = local_today()
        return HabitsOut(today=today, habits=[_out(s) for s in habits.statuses(session, today)])


@mcp.tool(title="Check habit", annotations=WRITE)
def check_habit(
    habit_id: Annotated[int, Field(ge=1, description="Habit id from list_habits")],
    done: Annotated[bool, Field(description="True to tick, False to untick")] = True,
    day: Annotated[date | None, Field(description="YYYY-MM-DD, default today")] = None,
) -> HabitOut:
    """Tick or untick a manual habit for today or an earlier day. Automatic habits (with a rule)
    are derived from data and cannot be ticked by hand."""
    target_day = day or local_today()
    args = {"habit_id": habit_id, "done": done, "day": target_day}
    with audited("check_habit", args) as session:
        habit = session.get(Habit, habit_id)
        if habit is None or habit.archived:
            raise ToolError(f"No active habit with id {habit_id}. Use list_habits to find it.")
        try:
            habits.check(session, habit, target_day, done)
        except habits.HabitError as exc:
            raise ToolError(str(exc)) from exc
        status = next(s for s in habits.statuses(session) if s.habit.id == habit.id)
        return _out(status)
