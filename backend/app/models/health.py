from datetime import date, datetime

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    PrimaryKeyConstraint,
    SmallInteger,
    String,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class HealthRecord(TimestampMixin, Base):
    """One Health Connect record as the bridge app sent it, for every type (sleep, steps, heart
    rate, exercise, nutrition, weight, ...). The derived tables below are built from these rows,
    so a mapping can be fixed later without syncing again. Types without a derived table yet
    (nutrition, weight) are only kept here."""

    __tablename__ = "health_records"
    __table_args__ = (Index("ix_health_records_type_local_date", "type", "local_date"),)

    # The Health Connect record id (a UUID), stable across edits of the record.
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    type: Mapped[str] = mapped_column(String(40))
    # Package of the app that wrote the record, e.g. com.huami.watch.hmwatchmanager (Zepp).
    source_app: Mapped[str] = mapped_column(String(200))
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # Local day the record counts for: the wake-up day for sleep, the start day otherwise.
    local_date: Mapped[date] = mapped_column(Date)
    last_modified: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    raw: Mapped[dict] = mapped_column(JSONB, server_default="{}")
    # Deleted in Health Connect. Kept so a late upsert of the same id does not revive it.
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SleepSession(Base):
    __tablename__ = "sleep_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    record_id: Mapped[str] = mapped_column(
        ForeignKey("health_records.id", ondelete="CASCADE"), unique=True
    )
    source_app: Mapped[str] = mapped_column(String(200))
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # Sleep over midnight counts for the day of waking up.
    local_date: Mapped[date] = mapped_column(Date, index=True)
    in_bed_minutes: Mapped[int] = mapped_column(Integer)
    # In bed minus awake stages; equals in_bed_minutes when the session has no stages.
    asleep_minutes: Mapped[int] = mapped_column(Integer)
    deep_minutes: Mapped[int | None] = mapped_column(Integer)
    light_minutes: Mapped[int | None] = mapped_column(Integer)
    rem_minutes: Mapped[int | None] = mapped_column(Integer)
    awake_minutes: Mapped[int | None] = mapped_column(Integer)
    # [{"start": iso, "end": iso, "stage": "deep" | "light" | "rem" | "awake" | ...}]
    stages: Mapped[list] = mapped_column(JSONB, server_default="[]")


class HeartRateSample(Base):
    __tablename__ = "heart_rate"
    __table_args__ = (
        PrimaryKeyConstraint("record_id", "time"),
        Index("ix_heart_rate_time", "time"),
    )

    record_id: Mapped[str] = mapped_column(ForeignKey("health_records.id", ondelete="CASCADE"))
    time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    bpm: Mapped[int] = mapped_column(SmallInteger)


class DailyMetrics(Base):
    """Per local day, recomputed from the records whenever a sync touches that day.

    Several apps can write the same steps or sleep (Zepp and Samsung Health, for example). Summing
    them would count twice, so a day takes the source with the largest total instead."""

    __tablename__ = "daily_metrics"

    local_date: Mapped[date] = mapped_column(Date, primary_key=True)
    steps: Mapped[int | None] = mapped_column(Integer)
    steps_source: Mapped[str | None] = mapped_column(String(200))
    kcal_burned: Mapped[int | None] = mapped_column(Integer)
    resting_hr: Mapped[int | None] = mapped_column(SmallInteger)
    hr_min: Mapped[int | None] = mapped_column(SmallInteger)
    hr_avg: Mapped[int | None] = mapped_column(SmallInteger)
    hr_max: Mapped[int | None] = mapped_column(SmallInteger)
    sleep_minutes: Mapped[int | None] = mapped_column(Integer)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
