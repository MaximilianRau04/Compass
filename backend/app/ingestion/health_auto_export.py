"""Apple Health data from the iOS app Health Auto Export (REST API automation, JSON).

Health Auto Export reads HealthKit on the iPhone and posts `{"data": {"metrics": [...],
"workouts": [...]}}` to a URL (format: help.healthyapps.dev/en/health-auto-export/export-format).
This module turns it into the records of the Health Connect ingest (app.ingestion.healthconnect),
so everything derived from them (sleep, heart rate, daily metrics, meals, weight, workouts) works
the same as on Android.

The export has no record ids, so each record gets one from what identifies the reading: metric,
source and time (plus the food for nutrition). The same reading sent again replaces itself. A time
group that grows while "Summarize Data" is on (today's steps of the current hour) does too.

Health Auto Export cannot report deletions: a reading deleted in Apple Health stays in Compass.
The native iOS bridge (ios/) can, and should be preferred when it is available.

Sleep arrives per phase when "Summarize Data" is off. The phases of one source are grouped into
nights (a new night after a gap of more than SLEEP_GAP) and keyed by source and day of waking up,
so a night that arrives in two exports is merged instead of replaced. With "Summarize Data" on a
night is only a total without phases; it still counts, but the hypnogram stays empty.
"""

import hashlib
import json
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.health import HealthRecord
from app.schemas.health import IngestPayload, IngestRecord
from app.services.clock import local_tz

SOURCE = "Health Auto Export"
SLEEP_GAP = timedelta(hours=2)
# What IngestPayload takes per batch.
BATCH_SIZE = 5000

# HealthKit sleep values as Health Auto Export names them -> stages of app.ingestion.healthconnect.
SLEEP_STAGES = {
    "core": "light",
    "deep": "deep",
    "rem": "rem",
    "awake": "awake",
    "asleep": "sleeping",
    "unspecified": "sleeping",
}
IN_BED = "in bed"

# Nutrition metric -> field of a nutrition record and its unit.
NUTRIENTS = {
    "dietary_energy": ("energy_kcal", "kcal"),
    "protein": ("protein_g", "g"),
    "carbohydrates": ("carbs_g", "g"),
    "total_fat": ("fat_g", "g"),
    "saturated_fat": ("saturated_fat_g", "g"),
    "fiber": ("fiber_g", "g"),
    "dietary_sugar": ("sugar_g", "g"),
    "sodium": ("sodium_mg", "mg"),
    "potassium": ("potassium_mg", "mg"),
    "calcium": ("calcium_mg", "mg"),
    "iron": ("iron_mg", "mg"),
}

# Metrics with one value per reading (see _simple).
SIMPLE = {
    "step_count",
    "resting_heart_rate",
    "heart_rate_variability",
    "blood_oxygen_saturation",
    "respiratory_rate",
    "walking_running_distance",
    "weight_body_mass",
}
ENERGY = {"active_energy", "basal_energy_burned"}

# Other names of the same metric, from older versions of the app.
ALIASES = {
    "body_mass": "weight_body_mass",
    "oxygen_saturation": "blood_oxygen_saturation",
    "walking_and_running_distance": "walking_running_distance",
    "active_energy_burned": "active_energy",
    "basal_energy": "basal_energy_burned",
    "carbohydrate": "carbohydrates",
    "dietary_carbohydrates": "carbohydrates",
    "dietary_protein": "protein",
    "dietary_fat_total": "total_fat",
    "dietary_fiber": "fiber",
}

_TO_GRAMS = {"g": 1.0, "mg": 0.001, "mcg": 1e-6, "µg": 1e-6, "ug": 1e-6, "kg": 1000.0}
_TO_KCAL = {"kcal": 1.0, "cal": 1.0, "kj": 1 / 4.184}
_TO_KG = {"kg": 1.0, "lb": 0.45359237, "lbs": 0.45359237, "g": 0.001, "st": 6.35029318}
_TO_METERS = {"m": 1.0, "km": 1000.0, "mi": 1609.344, "ft": 0.3048, "yd": 0.9144}


class Metric(BaseModel):
    name: str = Field(max_length=100)
    units: str = Field("", max_length=40)
    data: list[dict[str, Any]] = Field(default_factory=list)


class ExportData(BaseModel):
    metrics: list[Metric] = Field(default_factory=list)
    workouts: list[dict[str, Any]] = Field(default_factory=list)


class Export(BaseModel):
    data: ExportData = Field(default_factory=ExportData)


def parse_time(value: Any) -> datetime | None:
    """'2024-02-06 14:30:00 -0800' as the app writes it, or an ISO time; None without a zone."""
    if not isinstance(value, str):
        return None
    for parse in (lambda v: datetime.strptime(v, "%Y-%m-%d %H:%M:%S %z"), datetime.fromisoformat):
        try:
            parsed = parse(value.strip())
        except ValueError:
            continue
        if parsed.tzinfo is not None:
            return parsed
    return None


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return float(value)


def _convert(value: float | None, units: str, table: dict[str, float], target: str) -> float | None:
    """`value` in `units` converted to `target` (both keys of `table`); None for unknown units."""
    unit = units.strip().lower() or target
    if value is None or unit not in table:
        return None
    return value * table[unit] / table[target]


def _record_id(*parts: Any) -> str:
    digest = hashlib.sha256(json.dumps(parts, default=str).encode()).hexdigest()
    return f"hae:{digest[:40]}"


def _source(point: dict[str, Any]) -> str:
    return str(point.get("source") or "")[:200]


@dataclass
class Converted:
    records: list[IngestRecord] = field(default_factory=list)
    skipped: int = 0
    unknown: set[str] = field(default_factory=set)

    def add(
        self,
        record_id: str,
        kind: str,
        source: str,
        start: datetime,
        end: datetime | None,
        data: dict,
    ) -> None:
        self.records.append(
            IngestRecord(
                id=record_id,
                type=kind,
                source=source,
                start=start,
                end=end if end and end > start else None,
                data=data,
            )
        )


def _point_times(point: dict[str, Any]) -> tuple[datetime | None, datetime | None]:
    start = (
        parse_time(point.get("start"))
        or parse_time(point.get("startDate"))
        or parse_time(point.get("date"))
    )
    end = parse_time(point.get("end")) or parse_time(point.get("endDate"))
    return start, end


# --- Metrics with one value per reading --------------------------------------------------------


def _simple(name: str, units: str, point: dict[str, Any]) -> tuple[str, dict] | None:
    """Record type and data for a metric with a single `qty`, or None if it does not fit."""
    qty = _number(point.get("qty"))
    if name == "step_count":
        return ("steps", {"count": round(qty)}) if qty is not None else None
    if name == "resting_heart_rate":
        return ("resting_heart_rate", {"bpm": round(qty)}) if qty else None
    if name == "heart_rate_variability":
        # HealthKit measures SDNN; Health Connect sends RMSSD. They are not comparable.
        return ("heart_rate_variability_sdnn", {"sdnn_ms": qty}) if qty is not None else None
    if name == "blood_oxygen_saturation":
        if qty is None:
            return None
        # Percent; HealthKit itself stores a fraction, which some versions pass on.
        return "oxygen_saturation", {"percent": qty * 100 if qty <= 1 else qty}
    if name == "respiratory_rate":
        return ("respiratory_rate", {"rate": qty}) if qty is not None else None
    if name == "walking_running_distance":
        meters = _convert(qty, units, _TO_METERS, "m")
        return ("distance", {"meters": meters}) if meters is not None else None
    if name == "weight_body_mass":
        kg = _convert(qty, units, _TO_KG, "kg")
        return ("weight", {"kg": round(kg, 2)}) if kg else None
    return None


def _energy(name: str, units: str, point: dict[str, Any], out: Converted) -> None:
    """Active and resting energy. Health Connect has the total per reading; here the total of a
    day is active plus basal, so both also become total_calories records."""
    kcal = _convert(_number(point.get("qty")), units, _TO_KCAL, "kcal")
    start, end = _point_times(point)
    if kcal is None or start is None:
        out.skipped += 1
        return
    source = _source(point)
    if name == "active_energy":
        out.add(
            _record_id(name, source, start, end),
            "active_calories",
            source,
            start,
            end,
            {"kcal": kcal},
        )
    out.add(
        _record_id(name, "total", source, start, end),
        "total_calories",
        source,
        start,
        end,
        {"kcal": kcal},
    )


def _reading(name: str, units: str, point: dict[str, Any], out: Converted) -> None:
    mapped = _simple(name, units, point)
    start, end = _point_times(point)
    if mapped is None or start is None:
        out.skipped += 1
        return
    source = _source(point)
    out.add(_record_id(name, source, start, end), mapped[0], source, start, end, mapped[1])


def _heart_rate(point: dict[str, Any], out: Converted) -> None:
    """One sample per reading, at its average (a summarized time group has Min, Avg and Max)."""
    start, _ = _point_times(point)
    bpm = _number(point.get("Avg", point.get("avg", point.get("qty"))))
    if start is None or bpm is None or not 1 <= bpm <= 300:
        out.skipped += 1
        return
    source = _source(point)
    out.add(
        _record_id("heart_rate", source, start),
        "heart_rate",
        source,
        start,
        None,
        {"samples": [{"time": start.isoformat(), "bpm": round(bpm)}]},
    )


def _nutrient(name: str, units: str, point: dict[str, Any], out: Converted) -> None:
    key, unit = NUTRIENTS[name]
    qty = _number(point.get("qty"))
    value = (
        _convert(qty, units, _TO_KCAL, "kcal")
        if unit == "kcal"
        else _convert(qty, units, _TO_GRAMS, unit)
    )
    start, end = _point_times(point)
    if value is None or start is None:
        out.skipped += 1
        return
    source = _source(point)
    food = str(point.get("foodType") or "")[:200]
    data: dict[str, Any] = {"meal_type": "unknown", key: value}
    if food:
        data["name"] = food
    out.add(_record_id(name, source, start, end, food), "nutrition", source, start, end, data)


# --- Sleep -------------------------------------------------------------------------------------


@dataclass
class _Segment:
    start: datetime
    end: datetime
    value: str
    source: str

    def as_json(self) -> dict[str, str]:
        return {"start": self.start.isoformat(), "end": self.end.isoformat(), "value": self.value}


def _night_id(source: str, end: datetime) -> str:
    return _record_id("sleep", source, end.astimezone(local_tz()).date().isoformat())


def _stages(segments: list[_Segment]) -> list[dict[str, str]]:
    """The phases of a night, with the time in bed that no phase covers as awake_in_bed."""
    phases = sorted(
        (s for s in segments if s.value in SLEEP_STAGES), key=lambda s: (s.start, s.end)
    )
    stages = [
        {"start": s.start.isoformat(), "end": s.end.isoformat(), "stage": SLEEP_STAGES[s.value]}
        for s in phases
    ]
    covered_until = min(s.start for s in segments)
    for s in phases:
        if s.start > covered_until:
            stages.append(
                {
                    "start": covered_until.isoformat(),
                    "end": s.start.isoformat(),
                    "stage": "awake_in_bed",
                }
            )
        covered_until = max(covered_until, s.end)
    window_end = max(s.end for s in segments)
    if phases and window_end > covered_until:
        stages.append(
            {
                "start": covered_until.isoformat(),
                "end": window_end.isoformat(),
                "stage": "awake_in_bed",
            }
        )
    return sorted(stages, key=lambda s: s["start"])


def _sleep_segments(points: list[dict[str, Any]], out: Converted) -> list[_Segment]:
    segments = []
    for point in points:
        start, end = _point_times(point)
        value = str(point.get("value") or "").strip().lower()
        if (
            start is None
            or end is None
            or end <= start
            or (value not in SLEEP_STAGES and value != IN_BED)
        ):
            out.skipped += 1
            continue
        segments.append(_Segment(start, end, value, _source(point)))
    return segments


def _summarized_night(point: dict[str, Any], out: Converted) -> None:
    """A night as a total ("Summarize Data" on): asleep from sleepStart to sleepEnd, no phases."""
    start = parse_time(point.get("sleepStart")) or parse_time(point.get("inBedStart"))
    end = parse_time(point.get("sleepEnd")) or parse_time(point.get("inBedEnd"))
    if start is None or end is None or end <= start:
        out.skipped += 1
        return
    source = _source(point)
    out.add(_night_id(source, end), "sleep", source, start, end, {"stages": [], "summarized": True})


def _sleep(session: Session, points: list[dict[str, Any]], out: Converted) -> None:
    single = []
    for point in points:
        if "sleepStart" in point or "totalSleep" in point:
            _summarized_night(point, out)
        else:
            single.append(point)
    segments = _sleep_segments(single, out)

    by_source: dict[str, list[_Segment]] = defaultdict(list)
    for s in segments:
        by_source[s.source].append(s)
    nights: list[list[_Segment]] = []
    for source_segments in by_source.values():
        source_segments.sort(key=lambda s: s.start)
        current: list[_Segment] = []
        for s in source_segments:
            if current and s.start - max(c.end for c in current) > SLEEP_GAP:
                nights.append(current)
                current = []
            current.append(s)
        if current:
            nights.append(current)

    # A night that arrived in an earlier export keeps its phases: merge instead of replace.
    ids = {_night_id(n[0].source, max(s.end for s in n)): n for n in nights}
    stored = {
        r.id: r for r in session.scalars(select(HealthRecord).where(HealthRecord.id.in_(list(ids))))
    }
    for record_id, night in ids.items():
        source = night[0].source
        merged = {(s.start, s.end, s.value): s for s in night}
        previous = stored.get(record_id)
        for raw in ((previous.raw.get("data") or {}).get("segments") or []) if previous else []:
            start, end = parse_time(raw.get("start")), parse_time(raw.get("end"))
            if start and end:
                merged.setdefault(
                    (start, end, raw.get("value", "")),
                    _Segment(start, end, raw.get("value", ""), source),
                )
        segs = sorted(merged.values(), key=lambda s: s.start)
        start, end = min(s.start for s in segs), max(s.end for s in segs)
        out.add(
            record_id,
            "sleep",
            source,
            start,
            end,
            {"stages": _stages(segs), "segments": [s.as_json() for s in segs]},
        )


# --- Workouts ----------------------------------------------------------------------------------

# Words in Health Auto Export's workout names -> exercise names of the Health Connect ingest
# (app.services.health). Checked in order; the first match wins.
_WORKOUTS = [
    ("strength", "strength_training"),
    ("high intensity", "hiit"),
    ("hiit", "hiit"),
    ("cross training", "hiit"),
    ("core training", "calisthenics"),
    ("run", "running"),
    ("walk", "walking"),
    ("hik", "hiking"),
    ("cycl", "biking"),
    ("bik", "biking"),
    ("swim", "swimming_pool"),
    ("elliptical", "elliptical"),
    ("row", "rowing_machine"),
    ("stair", "stair_climbing_machine"),
    ("yoga", "yoga"),
    ("pilates", "pilates"),
    ("flexibility", "stretching"),
    ("cooldown", "stretching"),
    ("stretch", "stretching"),
    ("dance", "dancing"),
    ("soccer", "soccer"),
    ("basketball", "basketball"),
    ("table tennis", "table_tennis"),
    ("tennis", "tennis"),
    ("badminton", "badminton"),
    ("volleyball", "volleyball"),
    ("boxing", "boxing"),
    ("kickboxing", "boxing"),
    ("martial", "martial_arts"),
    ("climbing", "rock_climbing"),
]


def exercise_name(name: str, indoor: bool | None = None, location: str = "") -> str:
    lower = name.lower()
    for word, exercise in _WORKOUTS:
        if word in lower:
            if exercise == "running" and (indoor or "indoor" in lower or "treadmill" in lower):
                return "running_treadmill"
            if exercise == "biking" and (indoor or "indoor" in lower):
                return "biking_stationary"
            if exercise == "swimming_pool" and (
                location.lower() == "open water" or "open water" in lower
            ):
                return "swimming_open_water"
            return exercise
    # Anything else stays recognisable but does not count as strength training.
    slug = "".join(c if c.isalnum() else "_" for c in lower).strip("_")
    return slug[:40] or "other"


def _workout(workout: dict[str, Any], out: Converted) -> None:
    name = str(workout.get("name") or "")[:200]
    start = parse_time(workout.get("start"))
    end = parse_time(workout.get("end"))
    duration = _number(workout.get("duration"))
    if end is None and start is not None and duration:
        end = start + timedelta(seconds=duration)
    if start is None or end is None or end <= start:
        out.skipped += 1
        return
    source_info = workout.get("source")
    source = str(source_info.get("name") if isinstance(source_info, dict) else source_info or "")[
        :200
    ]
    workout_id = str(workout.get("id") or "")
    record_id = (
        f"hae:workout:{workout_id}"[:64] if workout_id else _record_id("workout", name, start)
    )
    indoor = workout.get("isIndoor") if isinstance(workout.get("isIndoor"), bool) else None
    data = {
        "exercise": exercise_name(name, indoor, str(workout.get("location") or "")),
        "title": name,
    }
    out.add(record_id, "exercise", source, start, end, data)


# --- Entry point -------------------------------------------------------------------------------


def convert(session: Session, export: Export) -> Converted:
    out = Converted()
    for metric in export.data.metrics:
        name = metric.name.strip().lower().replace(" ", "_")
        name = ALIASES.get(name, name)
        if name == "sleep_analysis":
            _sleep(session, metric.data, out)
        elif name == "heart_rate":
            for point in metric.data:
                _heart_rate(point, out)
        elif name in NUTRIENTS:
            for point in metric.data:
                _nutrient(name, metric.units, point, out)
        elif name in ENERGY:
            for point in metric.data:
                _energy(name, metric.units, point, out)
        elif name in SIMPLE:
            for point in metric.data:
                _reading(name, metric.units, point, out)
        else:
            # One of the 100+ metrics the app can export that Compass does not use.
            out.unknown.add(name[:100])
    for workout in export.data.workouts:
        _workout(workout, out)
    return out


def batches(converted: Converted, device: str | None) -> list[IngestPayload]:
    """The records in batches the Health Connect ingest takes (the last version of an id wins)."""
    records = list({r.id: r for r in converted.records}.values())
    chunks = [records[i : i + BATCH_SIZE] for i in range(0, len(records), BATCH_SIZE)] or [[]]
    return [
        IngestPayload(device=device or SOURCE, app_version=None, records=chunk) for chunk in chunks
    ]
