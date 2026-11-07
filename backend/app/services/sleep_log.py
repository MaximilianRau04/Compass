"""Nights entered by hand, for when the watch was not worn.

A night entered here is stored like one from Health Connect: a `health_records` row (source
"compass", id "compass:<uuid>") and the sleep session derived from it, so averages, the daily
metrics and the bedtime advice treat it like any other night. If the watch has the same night too,
the longer one counts, as with two apps. The bridge app's snapshots never remove these rows.
"""

import uuid
from datetime import timedelta

from pydantic import AwareDatetime, BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ingestion.healthconnect import _days, _derive_sleep
from app.models.health import HealthRecord, SleepSession
from app.services import health
from app.services.clock import local_tz, utc_now

MANUAL = "compass"
MAX_NIGHT = timedelta(hours=16)


class SleepLogError(ValueError):
    pass


class ManualNight(BaseModel):
    start_at: AwareDatetime = Field(description="Fell asleep (or went to bed)")
    end_at: AwareDatetime = Field(description="Woke up")
    awake_minutes: int = Field(0, ge=0, le=600, description="Lying awake during the night")


def add(session: Session, data: ManualNight) -> SleepSession:
    start, end = data.start_at, data.end_at
    if end <= start:
        raise SleepLogError("waking up has to come after falling asleep")
    if end - start > MAX_NIGHT:
        raise SleepLogError("a night is at most 16 hours")
    if end > utc_now() + timedelta(minutes=5):
        raise SleepLogError("the night lies in the future")
    in_bed = round((end - start).total_seconds() / 60)
    if data.awake_minutes >= in_bed:
        raise SleepLogError("more time awake than in bed")
    overlap = session.scalar(
        select(SleepSession.id).where(
            SleepSession.source_app == MANUAL,
            SleepSession.start_at < end,
            SleepSession.end_at > start,
        )
    )
    if overlap:
        raise SleepLogError("overlaps a night you already entered")

    record = HealthRecord(
        id=f"{MANUAL}:{uuid.uuid4()}",
        type="sleep",
        source_app=MANUAL,
        start_at=start,
        end_at=end,
        local_date=end.astimezone(local_tz()).date(),
        last_modified=utc_now(),
        raw={"manual": True, "data": {"stages": []}, "awake_minutes": data.awake_minutes},
    )
    session.add(record)
    session.flush()
    _derive_sleep(session, record)
    night = session.scalar(select(SleepSession).where(SleepSession.record_id == record.id))
    if data.awake_minutes:
        night.awake_minutes = data.awake_minutes
        night.asleep_minutes = in_bed - data.awake_minutes
    session.flush()
    health.recompute_days(session, _days(record))
    return night


def remove(session: Session, night_id: int) -> bool:
    """Only nights entered by hand can be removed; the watch's ones come from Health Connect."""
    night = session.get(SleepSession, night_id)
    if night is None or night.source_app != MANUAL:
        return False
    record = session.get(HealthRecord, night.record_id)
    days = _days(record)
    session.delete(night)
    session.flush()  # before the record, whose delete would cascade to the night
    session.delete(record)
    session.flush()
    health.recompute_days(session, days)
    return True


def recent(session: Session, days: int = 60) -> list[SleepSession]:
    since = utc_now() - timedelta(days=days)
    return list(
        session.scalars(
            select(SleepSession)
            .where(SleepSession.source_app == MANUAL, SleepSession.end_at >= since)
            .order_by(SleepSession.end_at.desc())
        )
    )
