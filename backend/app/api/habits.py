from datetime import date

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from app.api.deps import SessionDep
from app.models.habits import Habit
from app.services import habits

router = APIRouter(prefix="/habits", tags=["habits"])


class HabitRead(BaseModel):
    id: int
    name: str
    rule: str | None = Field(description="null: ticked by hand")
    done_today: bool
    streak: int = Field(description="Days in a row up to today")
    days: list[bool] = Field(description="The last 60 days, oldest first, today last")


class HabitCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    rule: str | None = None


class HabitCheckWrite(BaseModel):
    day: date
    done: bool


def _get(session, habit_id: int) -> Habit:
    habit = session.get(Habit, habit_id)
    if habit is None or habit.archived:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "habit not found")
    return habit


def _bad(exc: habits.HabitError) -> HTTPException:
    return HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc))


@router.get("", response_model=list[HabitRead])
def list_habits(session: SessionDep):
    return [
        HabitRead(
            id=s.habit.id,
            name=s.habit.name,
            rule=s.habit.rule,
            done_today=s.done_today,
            streak=s.streak,
            days=s.days,
        )
        for s in habits.statuses(session)
    ]


@router.post("", status_code=status.HTTP_201_CREATED)
def create_habit(data: HabitCreate, session: SessionDep) -> dict:
    try:
        habit = habits.create(session, data.name, data.rule)
    except habits.HabitError as exc:
        raise _bad(exc) from exc
    session.commit()
    return {"id": habit.id}


@router.put("/{habit_id}/check", status_code=status.HTTP_204_NO_CONTENT)
def check_habit(habit_id: int, data: HabitCheckWrite, session: SessionDep):
    try:
        habits.check(session, _get(session, habit_id), data.day, data.done)
    except habits.HabitError as exc:
        raise _bad(exc) from exc
    session.commit()


@router.delete("/{habit_id}", status_code=status.HTTP_204_NO_CONTENT)
def archive_habit(habit_id: int, session: SessionDep):
    """Hides the habit; its ticks stay."""
    habits.archive(session, _get(session, habit_id))
    session.commit()
