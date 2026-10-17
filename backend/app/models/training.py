from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class Exercise(TimestampMixin, Base):
    __tablename__ = "exercises"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), unique=True)
    muscle_group: Mapped[str | None] = mapped_column(String(60))
    # Sets without a weight count as bodyweight, not as 0 kg.
    bodyweight: Mapped[bool] = mapped_column(default=False)

    aliases: Mapped[list["ExerciseAlias"]] = relationship(
        back_populates="exercise", cascade="all, delete-orphan"
    )


class ExerciseAlias(Base):
    """Name as it appears in an export, mapped to the canonical exercise. Renaming an exercise
    in Gym Day creates a new name; merging it here keeps the progression in one line."""

    __tablename__ = "exercise_aliases"

    id: Mapped[int] = mapped_column(primary_key=True)
    alias: Mapped[str] = mapped_column(String(200), unique=True)
    exercise_id: Mapped[int] = mapped_column(
        ForeignKey("exercises.id", ondelete="CASCADE"), index=True
    )

    exercise: Mapped[Exercise] = relationship(back_populates="aliases")


class TrainingSession(TimestampMixin, Base):
    __tablename__ = "training_sessions"
    # A Gym Day session is identified by its start time plus the workout name.
    __table_args__ = (UniqueConstraint("started_at", "workout_name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    workout_name: Mapped[str] = mapped_column(String(120))
    # Filled later from Health Connect; the Gym Day export has no duration.
    duration_minutes: Mapped[int | None] = mapped_column(Integer)
    source: Mapped[str] = mapped_column(String(40), default="gymday")

    sets: Mapped[list["ExerciseSet"]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="ExerciseSet.id",
    )


class ExerciseSet(Base):
    __tablename__ = "exercise_sets"
    __table_args__ = (UniqueConstraint("session_id", "exercise_id", "set_index"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("training_sessions.id", ondelete="CASCADE"), index=True
    )
    exercise_id: Mapped[int] = mapped_column(
        ForeignKey("exercises.id", ondelete="CASCADE"), index=True
    )
    set_index: Mapped[int] = mapped_column(Integer)
    weight_kg: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    reps: Mapped[int | None] = mapped_column(Integer)
    rpe: Mapped[Decimal | None] = mapped_column(Numeric(3, 1))
    raw: Mapped[dict] = mapped_column(JSONB, server_default="{}")

    session: Mapped[TrainingSession] = relationship(back_populates="sets")
    exercise: Mapped[Exercise] = relationship(lazy="joined")
