from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, Numeric, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin

MACRO = Numeric(8, 1)


class NutritionMeal(TimestampMixin, Base):
    """Totals of one meal on one day from one source.

    Two sources: the MyFitnessPal export (backfill of the past) and Health Connect (ongoing,
    rebuilt from `health_records` whenever a sync touches the day). Both stay stored; for a day
    that has Health Connect meals, those win and the export rows of that day are ignored."""

    __tablename__ = "nutrition_meals"
    __table_args__ = (UniqueConstraint("source", "local_date", "meal"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(40))  # mfp_export | healthconnect
    local_date: Mapped[date] = mapped_column(Date, index=True)
    meal: Mapped[str] = mapped_column(String(20))  # breakfast | lunch | dinner | snack | unknown
    kcal: Mapped[Decimal] = mapped_column(MACRO)
    protein_g: Mapped[Decimal | None] = mapped_column(MACRO)
    carbs_g: Mapped[Decimal | None] = mapped_column(MACRO)
    fat_g: Mapped[Decimal | None] = mapped_column(MACRO)
    saturated_fat_g: Mapped[Decimal | None] = mapped_column(MACRO)
    fiber_g: Mapped[Decimal | None] = mapped_column(MACRO)
    sugar_g: Mapped[Decimal | None] = mapped_column(MACRO)
    sodium_mg: Mapped[Decimal | None] = mapped_column(MACRO)
    raw: Mapped[dict] = mapped_column(JSONB, server_default="{}")


class BodyWeight(TimestampMixin, Base):
    """One weight per day and source; like meals, Health Connect wins over the export."""

    __tablename__ = "body_weight"
    __table_args__ = (UniqueConstraint("source", "local_date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(40))
    local_date: Mapped[date] = mapped_column(Date, index=True)
    kg: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    # Time of the measurement; the export only has the day.
    measured_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Goal(Base):
    """A target like 2500 kcal per day, valid from a day until the next goal of the same metric."""

    __tablename__ = "goals"
    __table_args__ = (UniqueConstraint("metric", "valid_from"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    metric: Mapped[str] = mapped_column(String(40))  # kcal | protein_g | carbs_g | fat_g
    value: Mapped[Decimal] = mapped_column(Numeric(8, 1))
    valid_from: Mapped[date] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
