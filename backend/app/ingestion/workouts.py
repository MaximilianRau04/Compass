"""Strength exports of workout apps: sessions, exercises and sets.

The format is recognised by the columns of the CSV file: Gym Day (daily_strength.csv), Strong or
Hevy. To add one, write a parser that returns Row objects and list it in FORMATS.

The import is idempotent: a session is identified by its start time plus workout name, a set by
session, exercise and set number. The same or an overlapping export can be imported any number
of times; changed weights or reps are updated, nothing is duplicated.

Format notes: timestamps have no time zone and are local time. All weights end up in kg. An empty
weight means a bodyweight set, not 0 kg; Strong and Hevy write 0 for it. Their warm-up sets are
left out, and a file in pounds is only recognised where a column says so.
"""

import csv
import io
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import datetime
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.training import Exercise, ExerciseAlias, ExerciseSet, TrainingSession
from app.services import health, integrations
from app.services.clock import local_tz

LBS_TO_KG = Decimal("0.45359237")
MAX_BYTES = 5 * 1024 * 1024
UTC = ZoneInfo("UTC")


class WorkoutImportError(ValueError):
    """The file is not a usable export. The message is safe to show to the user."""


@dataclass(frozen=True)
class Row:
    started_at: datetime
    workout_name: str
    exercise: str
    set_index: int
    weight_kg: Decimal | None
    reps: int | None
    raw: dict
    duration_minutes: int | None = None


def _weight(value: str, unit: str, line: int) -> Decimal | None:
    value = value.strip().replace(",", ".")
    if not value:
        return None
    try:
        weight = Decimal(value)
    except InvalidOperation:
        raise WorkoutImportError(f"line {line}: weight {value!r} is not a number") from None
    unit = unit.strip().lower()
    if unit in ("lb", "lbs"):
        weight = (weight * LBS_TO_KG).quantize(Decimal("0.01"))
    elif unit not in ("kg", ""):
        raise WorkoutImportError(f"line {line}: unknown unit {unit!r}")
    return weight


def _time(value: str, formats: tuple[str, ...], line: int) -> datetime:
    for layout in formats:
        try:
            local = datetime.strptime(value.strip(), layout)
        except ValueError:
            continue
        return local.replace(tzinfo=local_tz()).astimezone(UTC)
    raise WorkoutImportError(f"line {line}: unreadable date {value!r}")


def _number(value: str | None, line: int) -> int | None:
    value = (value or "").strip()
    if not value:
        return None
    try:
        return int(float(value.replace(",", ".")))
    except ValueError:
        raise WorkoutImportError(f"line {line}: {value!r} is not a number") from None


def _clean(record: dict) -> dict:
    return {k: v for k, v in record.items() if k is not None}


def _numbered(rows: list[Row]) -> list[Row]:
    """Number the sets per session and exercise: an exercise done twice in a workout starts
    counting again in the export, and sets with the same number would overwrite each other."""
    seen: Counter = Counter()
    out = []
    for row in rows:
        key = (row.started_at, row.workout_name, row.exercise)
        seen[key] += 1
        out.append(replace(row, set_index=seen[key]))
    return out


def _gymday(reader: csv.DictReader) -> list[Row]:
    rows = []
    for line, record in enumerate(reader, start=2):
        name = (record["Exercise"] or "").strip()
        workout = (record["Workout name"] or "").strip()
        if not name or not record["Date"]:
            continue
        try:
            started = _time(record["Date"], ("%Y-%m-%d %H:%M:%S",), line)
            set_index = int(record["Set"])
            reps = int(record["Reps"]) if (record["Reps"] or "").strip() else None
        except (ValueError, WorkoutImportError):
            raise WorkoutImportError(f"line {line}: unreadable date, set or reps") from None
        rows.append(
            Row(
                started_at=started,
                workout_name=workout[:120] or "Training",
                exercise=name[:200],
                set_index=set_index,
                weight_kg=_weight(record["Weight"] or "", record["Measurement unit"] or "", line),
                reps=reps,
                raw=_clean(record),
            )
        )
    return rows


def _strong_minutes(value: str) -> int | None:
    """ "1h 5m", "45m", or seconds in the newer exports."""
    value = value.strip().lower()
    if value.isdigit():
        return round(int(value) / 60)
    if not value.endswith(("h", "m", "s")):
        return None
    minutes = 0.0
    for part in value.split():
        if part[:-1].isdigit():
            minutes += int(part[:-1]) * {"h": 60, "m": 1, "s": 1 / 60}.get(part[-1], 0)
    return round(minutes) or None


def _strong(reader: csv.DictReader) -> list[Row]:
    fields = reader.fieldnames or []
    weight_col = next(c for c in ("Weight (kg)", "Weight (lbs)", "Weight") if c in fields)
    fixed_unit = {"Weight (kg)": "kg", "Weight (lbs)": "lbs"}.get(weight_col)
    duration_col = next((c for c in ("Duration (sec)", "Duration") if c in fields), None)
    rows = []
    for line, record in enumerate(reader, start=2):
        name = (record["Exercise Name"] or "").strip()
        order = (record["Set Order"] or "").strip()
        # Besides numbers there are W (warm-up), D (drop set) and rest timer rows.
        if not name or not record["Date"] or not order.isdigit():
            continue
        reps = _number(record["Reps"], line)
        weight = _weight(
            record[weight_col] or "", fixed_unit or record.get("Weight Unit") or "", line
        )
        if not reps:
            continue  # cardio, timed or empty sets
        rows.append(
            Row(
                started_at=_time(record["Date"], ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"), line),
                workout_name=(record["Workout Name"] or "").strip()[:120] or "Training",
                exercise=name[:200],
                set_index=int(order),
                weight_kg=weight or None,
                reps=reps,
                raw=_clean(record),
                duration_minutes=_strong_minutes(record[duration_col] or "")
                if duration_col
                else None,
            )
        )
    return _numbered(rows)


def _hevy(reader: csv.DictReader) -> list[Row]:
    fields = reader.fieldnames or []
    weight_col = "weight_kg" if "weight_kg" in fields else "weight_lbs"
    unit = "kg" if weight_col == "weight_kg" else "lbs"
    layouts = ("%d %b %Y, %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S")
    rows = []
    for line, record in enumerate(reader, start=2):
        name = (record["exercise_title"] or "").strip()
        if not name or not record["start_time"] or record.get("set_type") == "warmup":
            continue
        reps = _number(record["reps"], line)
        weight = _weight(record[weight_col] or "", unit, line)
        if not reps:
            continue  # cardio, timed or empty sets
        started = _time(record["start_time"], layouts, line)
        duration = None
        if (record.get("end_time") or "").strip():
            ended = _time(record["end_time"], layouts, line)
            duration = round((ended - started).total_seconds() / 60)
        rows.append(
            Row(
                started_at=started,
                workout_name=(record["title"] or "").strip()[:120] or "Training",
                exercise=name[:200],
                set_index=0,  # counted from 0 per exercise; _numbered sets it
                weight_kg=weight or None,
                reps=reps,
                raw=_clean(record),
                duration_minutes=duration,
            )
        )
    return _numbered(rows)


@dataclass(frozen=True)
class Format:
    name: str  # also the source of its sessions
    columns: set[str]  # all of these
    any_of: set[str]  # at least one of these
    parse: Callable[[csv.DictReader], list[Row]]


FORMATS = (
    Format(
        health.GYMDAY_SESSION,
        {"Date", "Workout name", "Exercise", "Set", "Weight", "Reps", "Measurement unit"},
        set(),
        _gymday,
    ),
    Format(
        "strong",
        {"Date", "Workout Name", "Exercise Name", "Set Order", "Reps"},
        {"Weight", "Weight (kg)", "Weight (lbs)"},
        _strong,
    ),
    Format(
        "hevy",
        {"title", "start_time", "exercise_title", "reps"},
        {"weight_kg", "weight_lbs"},
        _hevy,
    ),
)


def parse_csv(data: bytes) -> tuple[Format, list[Row]]:
    if len(data) > MAX_BYTES:
        raise WorkoutImportError("file is larger than 5 MB")
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise WorkoutImportError("file is not UTF-8 text") from None
    header = text.split("\n", 1)[0]
    # Some apps write semicolons, depending on the phone's language.
    reader = csv.DictReader(io.StringIO(text), delimiter=";" if ";" in header else ",")
    fields = set(reader.fieldnames or [])
    for found in FORMATS:
        if found.columns <= fields and (not found.any_of or found.any_of & fields):
            rows = found.parse(reader)
            if not rows:
                raise WorkoutImportError("the file contains no sets")
            return found, rows
    names = ", ".join(sorted(fields))[:300]
    raise WorkoutImportError(
        f"not a workout export of Gym Day, Strong or Hevy (columns found: {names})"
    )


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
    found, rows = parse_csv(data)
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
            sessions[key] = TrainingSession(
                started_at=key[0], workout_name=key[1], source=found.name
            )
            session.add(sessions[key])
            sessions_created += 1
    for row in rows:
        current = sessions[(row.started_at, row.workout_name)]
        if row.duration_minutes and current.duration_minutes is None:
            current.duration_minutes = row.duration_minutes
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

    # Health Connect may already have the duration of these sessions (Gym Day writes it there).
    tz = local_tz()
    health.match_gymday_sessions(session, first.astimezone(tz).date(), last.astimezone(tz).date())
    health.match_watch_sessions(session, first.astimezone(tz).date(), last.astimezone(tz).date())
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
    integrations.record_success(session, found.name, stats)
    return stats
