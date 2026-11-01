"""Nutrition exports of diary apps: meals per day and weight, as backfill of the past.

An upload is a zip or a single CSV. Each CSV is recognised by its columns, not by its name. To add
an app, write a parser and list it in FORMATS.

- MyFitnessPal mails a zip with three CSV files whose names carry the date range, e.g.
  `Nährwerte-Übersicht-2022-07-11-bis-2026-10-16.csv`, with German or English headers: one row per
  day and meal, one per day with the weight (kg), and workouts, which are left out because they come
  from the Training tab and the watch.
- Cronometer writes one row per food (servings.csv) and the weight with its unit (biometrics.csv).
- Lose It! writes one row per food (food-logs.csv, in a zip) and keeps deleted entries, marked in a
  column. Its weights.csv names no unit, so it is left out: pounds must not become kilograms.

The Cronometer and Lose It! parsers are experimental: their columns come from open source tools
that read these exports, they have not been tested with real files yet.

The foods of a meal are summed. The import is idempotent over (source, day, meal) and (source, day):
the same or an overlapping export can be imported any number of times. Days without any row stay
empty (the app was not used), they are never 0 kcal.
"""

import csv
import io
import zipfile
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ingestion.workouts import LBS_TO_KG
from app.models.nutrition import BodyWeight, NutritionMeal
from app.services import integrations

MAX_BYTES = 10 * 1024 * 1024
TENTH = Decimal("0.1")
ISO = ("%Y-%m-%d",)
# Lose It! depends on the region of the account.
LOSE_IT_DATES = ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y", "%Y/%m/%d")
NO_VALUE = ("", "-", "n/a")

MEALS = {
    "frühstück": "breakfast",
    "mittagessen": "lunch",
    "abendessen": "dinner",
    "snacks": "snack",
    # English exports
    "breakfast": "breakfast",
    "lunch": "lunch",
    "dinner": "dinner",
    "snack": "snack",
}

# Column -> field, German and English headers.
MFP_COLUMNS = {
    "kcal": ("Kalorien", "Calories"),
    "protein_g": ("Eiweiß (g)", "Protein (g)"),
    "carbs_g": ("Kohlenhydrate (g)", "Carbohydrates (g)"),
    "fat_g": ("Fett (g)", "Fat (g)"),
    "saturated_fat_g": ("Gesättigte Fettsäuren", "Saturated Fat"),
    "fiber_g": ("Ballaststoffe", "Fiber"),
    "sugar_g": ("Zucker", "Sugar"),
    "sodium_mg": ("Natrium (mg)", "Sodium (mg)"),
}
CRONOMETER_COLUMNS = {
    "kcal": "Energy (kcal)",
    "protein_g": "Protein (g)",
    "carbs_g": "Carbs (g)",
    "fat_g": "Fat (g)",
    "saturated_fat_g": "Saturated (g)",
    "fiber_g": "Fiber (g)",
    "sugar_g": "Sugars (g)",
    "sodium_mg": "Sodium (mg)",
    "potassium_mg": "Potassium (mg)",
    "calcium_mg": "Calcium (mg)",
    "iron_mg": "Iron (mg)",
}
LOSE_IT_COLUMNS = {
    "kcal": "Calories",
    "protein_g": "Protein (g)",
    "carbs_g": "Carbohydrates (g)",
    "fat_g": "Fat (g)",
    "saturated_fat_g": "Saturated Fat (g)",
    "fiber_g": "Fiber (g)",
    "sugar_g": "Sugars (g)",
    "sodium_mg": "Sodium (mg)",
}
WORKOUT_COLUMNS = {"Workout name", "Exercise", "Exercise Name"}
LOSE_IT_WEIGHTS = {"Date", "Weight", "Deleted"}


class NutritionImportError(ValueError):
    """The upload is not a usable export. The message is safe to show to the user."""


@dataclass
class Parsed:
    meals: dict[tuple[date, str], dict] = field(default_factory=dict)
    weights: dict[date, Decimal] = field(default_factory=dict)
    ignored: list[str] = field(default_factory=list)
    source: str | None = None


def _number(value: str | None, where: str) -> Decimal | None:
    value = (value or "").strip().replace(",", ".")
    if value.lower() in NO_VALUE:
        return None
    try:
        return Decimal(value)
    except InvalidOperation:
        raise NutritionImportError(f"{where}: {value!r} is not a number") from None


def _day(value: str | None, where: str, layouts: tuple[str, ...] = ISO) -> date:
    for layout in layouts:
        try:
            return datetime.strptime((value or "").strip(), layout).date()
        except ValueError:
            continue
    raise NutritionImportError(f"{where}: unreadable date {value!r}")


def _column(fields: list[str], names: tuple[str, ...]) -> str | None:
    return next((n for n in names if n in fields), None)


def _add(out: Parsed, day: date, meal: str, values: dict, raw: dict) -> None:
    """Add a row to its meal. Fields no row of the meal has stay empty, they do not become 0."""
    row = out.meals.setdefault((day, MEALS.get(meal.lower(), "unknown")), dict.fromkeys(values))
    for name, value in values.items():
        if value is not None:
            row[name] = (row[name] or 0) + value
    row["raw"] = raw


def _mfp_columns(fields: list[str]) -> tuple[str | None, str | None, str | None]:
    return (
        _column(fields, ("Datum", "Date")),
        _column(fields, ("Mahlzeit", "Meal")),
        _column(fields, ("Gewicht", "Weight")),
    )


def _is_mfp(fields: list[str]) -> bool:
    date_col, meal_col, weight_col = _mfp_columns(fields)
    return bool(date_col and (meal_col or weight_col))


def _mfp(reader: csv.DictReader, name: str, out: Parsed) -> None:
    fields = reader.fieldnames or []
    date_col, meal_col, weight_col = _mfp_columns(fields)
    if not meal_col:
        for line, row in enumerate(reader, start=2):
            where = f"{name}, line {line}"
            kg = _number(row[weight_col], where)
            if kg is not None:
                out.weights[_day(row[date_col], where)] = kg
        return
    columns = {f: _column(fields, names) for f, names in MFP_COLUMNS.items()}
    if columns["kcal"] is None:
        raise NutritionImportError(f"{name}: nutrition file without a calories column")
    for line, row in enumerate(reader, start=2):
        where = f"{name}, line {line}"
        day = _day(row[date_col], where)
        values = {f: _number(row[c], where) if c else None for f, c in columns.items()}
        if values["kcal"] is not None:
            _add(
                out, day, (row[meal_col] or "").strip(), values, {k: v for k, v in row.items() if k}
            )


def _foods(
    reader: csv.DictReader,
    name: str,
    out: Parsed,
    columns: dict[str, str],
    date_col: str,
    meal_col: str,
    skip: Callable[[dict], bool],
    layouts: tuple[str, ...] = ISO,
) -> None:
    """A file with one row per food. Those rows would be large and add little, so no raw data."""
    fields = reader.fieldnames or []
    for line, row in enumerate(reader, start=2):
        if skip(row):
            continue
        where = f"{name}, line {line}"
        values = {f: _number(row[c], where) if c in fields else None for f, c in columns.items()}
        if values["kcal"] is not None:
            meal = (row.get(meal_col) or "").strip()
            _add(out, _day(row[date_col], where, layouts), meal, values, {})


def _cronometer(reader: csv.DictReader, name: str, out: Parsed) -> None:
    def is_total(row: dict) -> bool:
        # Tools that read this export report per-day totals in the group column.
        return (row.get("Group") or "").strip().lower() == "total"

    _foods(reader, name, out, CRONOMETER_COLUMNS, "Day", "Group", is_total)


def _cronometer_weight(reader: csv.DictReader, name: str, out: Parsed) -> None:
    for line, row in enumerate(reader, start=2):
        if (row["Metric"] or "").strip().lower() != "weight":
            continue
        where = f"{name}, line {line}"
        value = _number(row["Amount"], where)
        if value is None:
            continue
        unit = (row["Unit"] or "").strip().lower()
        if unit in ("lb", "lbs"):
            value = (value * LBS_TO_KG).quantize(Decimal("0.01"))
        elif unit != "kg":
            raise NutritionImportError(f"{where}: unknown unit {unit!r}")
        out.weights[_day(row["Day"], where)] = value


def _lose_it(reader: csv.DictReader, name: str, out: Parsed) -> None:
    def is_deleted(row: dict) -> bool:
        return (row.get("Deleted") or "").strip().lower() in ("true", "1", "yes")

    _foods(reader, name, out, LOSE_IT_COLUMNS, "Date", "Meal", is_deleted, LOSE_IT_DATES)


@dataclass(frozen=True)
class Format:
    source: str  # stored with its meals and weights
    matches: Callable[[list[str]], bool]
    parse: Callable[[csv.DictReader, str, Parsed], None]


# In this order: food-logs.csv of Lose It! has the date, meal and calories columns of MyFitnessPal.
FORMATS = (
    Format(
        "loseit_export",
        lambda fields: {"Date", "Name", "Meal", "Calories", "Deleted"} <= set(fields),
        _lose_it,
    ),
    Format(
        "cronometer_export",
        lambda fields: {"Day", "Food Name", "Energy (kcal)"} <= set(fields),
        _cronometer,
    ),
    Format(
        "cronometer_export",
        lambda fields: {"Day", "Metric", "Unit", "Amount"} <= set(fields),
        _cronometer_weight,
    ),
    Format("mfp_export", _is_mfp, _mfp),
)


def _parse_csv(name: str, data: bytes, out: Parsed, in_zip: bool = False) -> None:
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise NutritionImportError(f"{name}: not UTF-8 text") from None
    reader = csv.DictReader(io.StringIO(text))
    fields = reader.fieldnames or []
    found = next((f for f in FORMATS if f.matches(fields)), None)

    reason = None
    if WORKOUT_COLUMNS & set(fields):
        # Has "Date" and "Weight" too; without this check its sets would become body weights.
        reason = "this is a workout export, import it in the Training tab"
    elif set(fields) >= LOSE_IT_WEIGHTS:
        reason = "Lose It! weights name no unit, so they are left out"
    elif found is None:
        columns = ", ".join(sorted(fields))[:300]
        reason = (
            "not a nutrition export of MyFitnessPal, Cronometer or Lose It! "
            f"(columns found: {columns})"
        )
    if reason:
        if not in_zip:
            raise NutritionImportError(f"{name}: {reason}")
        out.ignored.append(name)
        return

    if out.source not in (None, found.source):
        raise NutritionImportError("the zip mixes exports of different apps")
    out.source = found.source
    found.parse(reader, name, out)


def parse(data: bytes, filename: str = "export.csv") -> Parsed:
    if len(data) > MAX_BYTES:
        raise NutritionImportError("file is larger than 10 MB")
    out = Parsed()
    if data[:2] == b"PK":
        try:
            archive = zipfile.ZipFile(io.BytesIO(data))
        except zipfile.BadZipFile:
            raise NutritionImportError("broken zip file") from None
        csvs = [i for i in archive.infolist() if i.filename.lower().endswith(".csv")]
        if not csvs:
            raise NutritionImportError("the zip contains no CSV files")
        for info in csvs:
            if info.file_size > MAX_BYTES:
                raise NutritionImportError(f"{info.filename}: larger than 10 MB")
            _parse_csv(info.filename.rsplit("/", 1)[-1], archive.read(info), out, in_zip=True)
    else:
        _parse_csv(filename, data, out)
    if not out.meals and not out.weights:
        raise NutritionImportError("the export contains no nutrition or weight values")
    # As stored, or every food app would count as changed on each import: they write many digits.
    for meal in out.meals.values():
        for name, value in meal.items():
            if isinstance(value, Decimal):
                meal[name] = value.quantize(TENTH)
    return out


def import_export(session: Session, data: bytes, filename: str = "export.csv") -> dict:
    parsed = parse(data, filename)
    source = parsed.source
    days = {d for d, _ in parsed.meals} | set(parsed.weights)

    existing = {
        (m.local_date, m.meal): m
        for m in session.scalars(
            select(NutritionMeal).where(
                NutritionMeal.source == source, NutritionMeal.local_date.in_(days)
            )
        )
    }
    created = updated = unchanged = 0
    for (day, meal), values in parsed.meals.items():
        row = existing.get((day, meal))
        if row is None:
            session.add(NutritionMeal(source=source, local_date=day, meal=meal, **values))
            created += 1
            continue
        if all(getattr(row, k) == v for k, v in values.items() if k != "raw"):
            unchanged += 1
            continue
        for k, v in values.items():
            setattr(row, k, v)
        updated += 1

    weights = {
        w.local_date: w
        for w in session.scalars(
            select(BodyWeight).where(
                BodyWeight.source == source, BodyWeight.local_date.in_(set(parsed.weights))
            )
        )
    }
    weights_created = 0
    for day, kg in parsed.weights.items():
        row = weights.get(day)
        if row is None:
            session.add(BodyWeight(source=source, local_date=day, kg=kg))
            weights_created += 1
        elif row.kg != kg:
            row.kg = kg
    session.flush()

    meal_days = sorted({d for d, _ in parsed.meals})
    stats = {
        "meals_created": created,
        "meals_updated": updated,
        "meals_unchanged": unchanged,
        "days": len(meal_days),
        "weights": len(parsed.weights),
        "weights_created": weights_created,
        "first": min(days).isoformat(),
        "last": max(days).isoformat(),
        "ignored_files": parsed.ignored,
    }
    integrations.record_success(session, source, stats)
    return stats
