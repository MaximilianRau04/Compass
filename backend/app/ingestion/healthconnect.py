"""Health Connect records pushed by the bridge app on the phone (android/).

Health Connect only lives on the device, so the app reads the changes since its last run and
posts them here. The import is idempotent over the Health Connect record id: the same batch can
arrive any number of times (the app retries after network errors), an edited record replaces the
old version, a deletion marks the record as deleted and removes what was derived from it.

The app sends a record only if Health Connect still had it when the app read it, so a record
always wins over a deletion of the same id: within one batch (the first app version did not keep
the order of the two), and later, when a deleted id comes back. Zepp deletes and rewrites a night
when it re-syncs the watch, and Health Connect gives the rewritten record the same id (derived
from Zepp's own record id), so without this the night would stay deleted.

The change feed alone did not get every rewrite through (21.10.2026: Zepp wrote the night in
three versions under new ids, the last one never arrived). So the app also sends a snapshot of the
small types (sleep, exercise, nutrition, weight) for the last days with every sync: whatever is
listed is stored, a record of that type and range that is not listed is marked deleted.

Every record is kept as it arrived (`health_records.raw`). Derived from it: sleep sessions with
stages, heart rate samples, the daily metrics of each touched day, the duration of Gym Day
sessions, and the meals and weights of each touched day (app.services.nutrition).
"""

import logging
from datetime import date, datetime
from typing import Any

from pydantic import AwareDatetime, BaseModel, Field, ValidationError
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models.health import HealthRecord, HeartRateSample, SleepSession
from app.schemas.health import IngestPayload, IngestRecord
from app.services import health, integrations, nutrition
from app.services.clock import local_tz, utc_now

log = logging.getLogger("compass.healthconnect")

MAX_BYTES = 20 * 1024 * 1024
AWAKE_STAGES = {"awake", "awake_in_bed", "out_of_bed"}
STAGE_COLUMNS = {"deep": "deep_minutes", "light": "light_minutes", "rem": "rem_minutes"}


class Stage(BaseModel):
    start: AwareDatetime
    end: AwareDatetime
    stage: str = Field(max_length=40)


class SleepData(BaseModel):
    stages: list[Stage] = Field(default_factory=list)


class Sample(BaseModel):
    time: AwareDatetime
    bpm: int = Field(ge=1, le=300)


class HeartRateData(BaseModel):
    samples: list[Sample] = Field(default_factory=list)


def local_day(record: IngestRecord) -> date:
    """Sleep counts for the day of waking up, everything else for the day it started."""
    when = (record.end or record.start) if record.type == "sleep" else record.start
    return when.astimezone(local_tz()).date()


def _minutes(start: datetime, end: datetime) -> int:
    return max(0, round((end - start).total_seconds() / 60))


def _derive_sleep(session: Session, row: HealthRecord) -> None:
    data = SleepData.model_validate(row.raw.get("data") or {})
    stages = sorted((s for s in data.stages if s.end > s.start), key=lambda s: s.start)
    in_bed = _minutes(row.start_at, row.end_at)
    per_stage: dict[str, int] = {}
    for s in stages:
        start, end = max(s.start, row.start_at), min(s.end, row.end_at)
        if end > start:
            per_stage[s.stage] = per_stage.get(s.stage, 0) + _minutes(start, end)
    awake = sum(m for stage, m in per_stage.items() if stage in AWAKE_STAGES)
    has_phases = any(stage in STAGE_COLUMNS for stage in per_stage)

    sleep = session.scalar(select(SleepSession).where(SleepSession.record_id == row.id))
    if sleep is None:
        sleep = SleepSession(record_id=row.id)
        session.add(sleep)
    sleep.source_app = row.source_app
    sleep.start_at, sleep.end_at, sleep.local_date = row.start_at, row.end_at, row.local_date
    sleep.in_bed_minutes = in_bed
    sleep.asleep_minutes = max(0, in_bed - awake)
    sleep.awake_minutes = awake if stages else None
    for stage, column in STAGE_COLUMNS.items():
        setattr(sleep, column, per_stage.get(stage, 0) if has_phases else None)
    sleep.stages = [s.model_dump(mode="json") for s in stages]


def _derive_heart_rate(session: Session, row: HealthRecord) -> set[date]:
    data = HeartRateData.model_validate(row.raw.get("data") or {})
    session.execute(delete(HeartRateSample).where(HeartRateSample.record_id == row.id))
    samples = {s.time: s.bpm for s in data.samples}
    session.add_all(HeartRateSample(record_id=row.id, time=t, bpm=b) for t, b in samples.items())
    tz = local_tz()
    return {t.astimezone(tz).date() for t in samples}


DERIVED = {"sleep": _derive_sleep, "heart_rate": _derive_heart_rate}


def _remove_derived(session: Session, row: HealthRecord) -> None:
    session.execute(delete(SleepSession).where(SleepSession.record_id == row.id))
    session.execute(delete(HeartRateSample).where(HeartRateSample.record_id == row.id))


def _days(row: HealthRecord) -> set[date]:
    tz = local_tz()
    return {row.local_date, row.start_at.astimezone(tz).date(), row.end_at.astimezone(tz).date()}


def ingest(session: Session, payload: IngestPayload) -> dict[str, Any]:
    now = utc_now()
    # The last version of an id within one batch wins.
    records = {r.id: r for r in payload.records}
    ids = set(records) | set(payload.deleted)
    existing = {
        r.id: r for r in session.scalars(select(HealthRecord).where(HealthRecord.id.in_(ids)))
    }

    touched: set[date] = set()
    exercise_touched = False
    created = updated = unchanged = invalid = deleted = restored = 0
    for record in records.values():
        row = existing.get(record.id)
        raw = record.model_dump(mode="json")
        if row is not None and row.deleted_at is None and row.raw == raw:
            unchanged += 1
            continue
        if row is None:
            row = HealthRecord(id=record.id)
            session.add(row)
            existing[record.id] = row
            created += 1
        else:
            if row.deleted_at is not None:
                # Health Connect has it again (see the module docstring).
                row.deleted_at = None
                restored += 1
            else:
                updated += 1
            touched |= _days(row)
        row.type = record.type
        row.source_app = record.source
        row.start_at = record.start
        row.end_at = max(record.end or record.start, record.start)
        row.local_date = local_day(record)
        row.last_modified = record.last_modified
        row.raw = raw
        touched |= _days(row)
        exercise_touched |= record.type == "exercise"

        derive = DERIVED.get(record.type)
        if derive is None:
            continue
        try:
            with session.begin_nested():
                extra = derive(session, row)
                session.flush()
        except ValidationError as exc:
            # Keep the raw record (the mapping can be fixed later), but do not block the sync.
            invalid += 1
            log.warning("record %s (%s) not derived: %s", record.id, record.type, exc)
            continue
        if extra:
            touched |= extra

    for record_id in payload.deleted:
        row = existing.get(record_id)
        if row is None or row.deleted_at is not None or record_id in records:
            continue
        row.deleted_at = now
        _remove_derived(session, row)
        touched |= _days(row)
        exercise_touched |= row.type == "exercise"
        deleted += 1
    for snapshot in payload.snapshots:
        keep = set(snapshot.ids) | set(records)
        gone = session.scalars(
            select(HealthRecord).where(
                HealthRecord.type == snapshot.type,
                HealthRecord.start_at >= snapshot.since,
                HealthRecord.deleted_at.is_(None),
                HealthRecord.id.not_in(keep),
            )
        )
        for row in gone:
            row.deleted_at = now
            _remove_derived(session, row)
            touched |= _days(row)
            exercise_touched |= row.type == "exercise"
            deleted += 1
    session.flush()

    health.recompute_days(session, touched)
    nutrition.rebuild_from_healthconnect(session, touched)
    if exercise_touched and touched:
        health.match_gymday_sessions(session, min(touched), max(touched))
    if touched:
        # Also when only heart rate came in: it may belong to a session synced earlier.
        health.match_watch_sessions(session, min(touched), max(touched))

    stats = {
        "received": len(payload.records),
        "created": created,
        "updated": updated,
        "unchanged": unchanged,
        "deleted": deleted,
        "restored": restored,
        "invalid": invalid,
        "days": len(touched),
    }
    integrations.record_success(
        session,
        "healthconnect",
        {
            **stats,
            "device": payload.device,
            "app_version": payload.app_version,
            "first_day": min(touched).isoformat() if touched else None,
            "last_day": max(touched).isoformat() if touched else None,
        },
    )
    return stats
