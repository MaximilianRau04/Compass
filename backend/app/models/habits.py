from datetime import date

from sqlalchemy import Boolean, Date, ForeignKey, Integer, SmallInteger, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class Habit(TimestampMixin, Base):
    """Something to do every day. A manual habit is ticked by hand; one with a rule is ticked by
    Compass from the day's data (steps goal, protein goal, enough sleep, a journal entry)."""

    __tablename__ = "habits"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    # None: manual; else steps_goal | protein_goal | sleep_need | journal
    rule: Mapped[str | None] = mapped_column(String(30))
    sort_order: Mapped[int] = mapped_column(SmallInteger, default=0)
    archived: Mapped[bool] = mapped_column(Boolean, default=False)


class HabitCheck(Base):
    """A manual habit ticked on a day."""

    __tablename__ = "habit_checks"

    habit_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("habits.id", ondelete="CASCADE"), primary_key=True
    )
    local_date: Mapped[date] = mapped_column(Date, primary_key=True)
