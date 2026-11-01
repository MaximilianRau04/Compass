from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, Numeric, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin

MACRO = Numeric(8, 1)


class NutritionMeal(TimestampMixin, Base):
    """Totals of one meal on one day from one source.

    Two kinds of source: exports of nutrition apps (backfill of the past) and Health Connect
    (ongoing, rebuilt from `health_records` whenever a sync touches the day). Both stay stored; for
    a day that has Health Connect meals, those win and the export rows of that day are ignored."""

    __tablename__ = "nutrition_meals"
    __table_args__ = (UniqueConstraint("source", "local_date", "meal"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(40))  # healthconnect | <app>_export
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
    # Not from MyFitnessPal: its export gives calcium and iron as % of the daily value.
    potassium_mg: Mapped[Decimal | None] = mapped_column(MACRO)
    calcium_mg: Mapped[Decimal | None] = mapped_column(MACRO)
    iron_mg: Mapped[Decimal | None] = mapped_column(MACRO)
    raw: Mapped[dict] = mapped_column(JSONB, server_default="{}")


class BodyWeight(TimestampMixin, Base):
    """One weight per day and source: manual (entered in Compass, in the morning), healthconnect
    (MFP or a scale app, the earliest of the day) or an export. Per day manual wins, then Health
    Connect, then the export, so the same weigh-in from two sources never counts twice."""

    __tablename__ = "body_weight"
    __table_args__ = (UniqueConstraint("source", "local_date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(40))
    local_date: Mapped[date] = mapped_column(Date, index=True)
    kg: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    # Time of the measurement; the export only has the day.
    measured_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class BodyMeasurement(TimestampMixin, Base):
    """A body measurement entered by hand, e.g. the waist once a week. One per metric and day."""

    __tablename__ = "body_measurements"
    __table_args__ = (UniqueConstraint("metric", "local_date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    metric: Mapped[str] = mapped_column(String(40))  # waist_cm
    local_date: Mapped[date] = mapped_column(Date, index=True)
    value: Mapped[Decimal] = mapped_column(Numeric(6, 1))


class Goal(Base):
    """A target like 2500 kcal per day, valid from a day until the next goal of the same metric."""

    __tablename__ = "goals"
    __table_args__ = (UniqueConstraint("metric", "valid_from"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    # kcal, protein_g, carbs_g, fat_g, steps, hr_max, weight_loss_min, weight_loss_max
    metric: Mapped[str] = mapped_column(String(40))
    value: Mapped[Decimal] = mapped_column(Numeric(8, 1))
    valid_from: Mapped[date] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
