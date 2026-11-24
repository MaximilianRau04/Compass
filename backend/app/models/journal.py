from datetime import date

from sqlalchemy import CheckConstraint, Date, SmallInteger, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin
from app.models.vector import Vector


class JournalEntry(TimestampMixin, Base):
    """One entry per day: how it felt (mood and energy from 1 to 5) and a free text. Saving the
    same day again replaces it."""

    __tablename__ = "journal_entries"
    __table_args__ = (
        CheckConstraint("mood BETWEEN 1 AND 5", name="mood"),
        CheckConstraint("energy BETWEEN 1 AND 5", name="energy"),
    )

    local_date: Mapped[date] = mapped_column(Date, primary_key=True)
    mood: Mapped[int | None] = mapped_column(SmallInteger)
    energy: Mapped[int | None] = mapped_column(SmallInteger)
    text: Mapped[str] = mapped_column(Text, server_default="")
    embedding: Mapped[list[float] | None] = mapped_column(Vector, nullable=True)
