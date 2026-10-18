"""Gym Day strength export (daily_strength.csv): sessions, exercises and sets.

The import is idempotent: a session is identified by its start time plus workout name, a set by
session, exercise and set number. The same or an overlapping export can be imported any number
of times; changed weights or reps are updated, nothing is duplicated.

Format notes: timestamps have no time zone and are local time. All weights are in kg (lbs is
converted). An empty weight means a bodyweight set, not 0 kg.
"""

import csv
import io
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.training import Exercise, ExerciseAlias, ExerciseSet, TrainingSession
from app.services import health, integrations
from app.services.clock import local_tz

REQUIRED = {"Date", "Workout name", "Exercise", "Set", "Weight", "Reps", "Measurement unit"}
LBS_TO_KG = Decimal("0.45359237")
MAX_BYTES = 5 * 1024 * 1024
UTC = ZoneInfo("UTC")


class GymDayImportError(ValueError):
    """The file is not a usable Gym Day export. The message is safe to show to the user."""


@dataclass(frozen=True)
class Row:
    started_at: datetime
    workout_name: str
    exercise: str
    set_index: int
    weight_kg: Decimal | None
    reps: int | None
    raw: dict


def _weight(value: str, unit: str, line: int) -> Decimal | None:
    value = value.strip().replace(",", ".")
    if not value:
        return None
    try:
        weight = Decimal(value)
    except InvalidOperation:
        raise GymDayImportError(f"line {line}: weight {value!r} is not a number") from None
    unit = unit.strip().lower()
    if unit in ("lb", "lbs"):
        weight = (weight * LBS_TO_KG).quantize(Decimal("0.01"))
    elif unit not in ("kg", ""):
        raise GymDayImportError(f"line {line}: unknown unit {unit!r}")
    return weight


def parse_csv(data: bytes) -> list[Row]:
    if len(data) > MAX_BYTES:
        raise GymDayImportError("file is larger than 5 MB")
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise GymDayImportError("file is not UTF-8 text") from None
    reader = csv.DictReader(io.StringIO(text))
    missing = REQUIRED - set(reader.fieldnames or [])
    if missing:
        raise GymDayImportError(
            "not a Gym Day strength export (missing columns: " + ", ".join(sorted(missing)) + ")"
        )

    tz = local_tz()
    rows = []
    for line, record in enumerate(reader, start=2):
        name = (record["Exercise"] or "").strip()
        workout = (record["Workout name"] or "").strip()
        if not name or not record["Date"]:
            continue
        try:
            local = datetime.strptime(record["Date"].strip(), "%Y-%m-%d %H:%M:%S")
            set_index = int(record["Set"])
            reps = int(record["Reps"]) if (record["Reps"] or "").strip() else None
        except ValueError:
            raise GymDayImportError(f"line {line}: unreadable date, set or reps") from None
        rows.append(
            Row(
                started_at=local.replace(tzinfo=tz).astimezone(UTC),
                workout_name=workout[:120] or "Training",
                exercise=name[:200],
                set_index=set_index,
                weight_kg=_weight(record["Weight"] or "", record["Measurement unit"] or "", line),
                reps=reps,
                raw={k: v for k, v in record.items() if k is not None},
            )
        )
    if not rows:
        raise GymDayImportError("the file contains no sets")
    return rows


def _resolve_exercises(session: Session, rows: list[Row]) -> tuple[dict[str, Exercise], int]:
    aliases = {
        a.alias: a.exercise
        for a in session.scalars(
            select(ExerciseAlias).where(ExerciseAlias.alias.in_({r.exercise for r in rows}))
        )
    }
    created = 0
    for row in rows:
        if row.exercise in aliases:
            continue
        exercise = session.scalar(select(Exercise).where(Exercise.name == row.exercise))
        if exercise is None:
            exercise = Exercise(name=row.exercise, bodyweight=row.weight_kg is None)
            session.add(exercise)
            created += 1
        session.add(ExerciseAlias(alias=row.exercise, exercise=exercise))
        aliases[row.exercise] = exercise
    session.flush()
    return aliases, created


def import_csv(session: Session, data: bytes) -> dict:
    rows = parse_csv(data)
    exercises, exercises_created = _resolve_exercises(session, rows)

    first, last = min(r.started_at for r in rows), max(r.started_at for r in rows)
    sessions = {
        (s.started_at, s.workout_name): s
        for s in session.scalars(
            select(TrainingSession).where(
                TrainingSession.started_at >= first, TrainingSession.started_at <= last
            )
        )
    }
    sessions_created = 0
    for key in dict.fromkeys((r.started_at, r.workout_name) for r in rows):
        if key not in sessions:
            sessions[key] = TrainingSession(started_at=key[0], workout_name=key[1])
            session.add(sessions[key])
            sessions_created += 1
    session.flush()

    session_ids = [s.id for s in sessions.values()]
    existing = {
        (s.session_id, s.exercise_id, s.set_index): s
        for s in session.scalars(select(ExerciseSet).where(ExerciseSet.session_id.in_(session_ids)))
    }
    created = updated = unchanged = 0
    for row in rows:
        key = (
            sessions[(row.started_at, row.workout_name)].id,
            exercises[row.exercise].id,
            row.set_index,
        )
        current = existing.get(key)
        if current is None:
            current = ExerciseSet(
                session_id=key[0],
                exercise_id=key[1],
                set_index=key[2],
                weight_kg=row.weight_kg,
                reps=row.reps,
                raw=row.raw,
            )
            session.add(current)
            existing[key] = current
            created += 1
        elif current.weight_kg != row.weight_kg or current.reps != row.reps:
            current.weight_kg, current.reps, current.raw = row.weight_kg, row.reps, row.raw
            updated += 1
        else:
            unchanged += 1
    session.flush()

    # Health Connect may already have the duration of these sessions.
    tz = local_tz()
    health.match_gymday_sessions(session, first.astimezone(tz).date(), last.astimezone(tz).date())
    stats = {
        "rows": len(rows),
        "sessions_created": sessions_created,
        "sets_created": created,
        "sets_updated": updated,
        "sets_unchanged": unchanged,
        "exercises_created": exercises_created,
        "first": first.astimezone(tz).date().isoformat(),
        "last": last.astimezone(tz).date().isoformat(),
    }
    integrations.record_success(session, "gymday", stats)
    return stats
