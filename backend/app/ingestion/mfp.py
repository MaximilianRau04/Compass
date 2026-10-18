"""MyFitnessPal data export: nutrition per meal and weight, as backfill of the past.

MFP mails a zip with three CSV files whose names carry the date range, e.g.
`Nährwerte-Übersicht-2022-07-11-bis-2026-10-16.csv`. Headers are German. The importer takes the zip
or a single CSV and recognises the files by their columns, not by their names:

- nutrition: one row per day and meal (Frühstück, Mittagessen, Abendessen, Snacks)
- weight: one row per day (kg)
- workouts: ignored, workouts come from Gym Day and Zepp

The import is idempotent over (day, meal) and day: the same or an overlapping export can be imported
any number of times. Days without any row stay empty (MFP was not used), they are never 0 kcal.
"""

import csv
import io
import zipfile
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.nutrition import BodyWeight, NutritionMeal
from app.services import integrations

SOURCE = "mfp_export"
MAX_BYTES = 10 * 1024 * 1024

MEALS = {
    "frühstück": "breakfast",
    "mittagessen": "lunch",
    "abendessen": "dinner",
    "snacks": "snack",
    # English export
    "breakfast": "breakfast",
    "lunch": "lunch",
    "dinner": "dinner",
}

# Column -> field, German and English headers.
NUTRITION_COLUMNS = {
    "kcal": ("Kalorien", "Calories"),
    "protein_g": ("Eiweiß (g)", "Protein (g)"),
    "carbs_g": ("Kohlenhydrate (g)", "Carbohydrates (g)"),
    "fat_g": ("Fett (g)", "Fat (g)"),
    "saturated_fat_g": ("Gesättigte Fettsäuren", "Saturated Fat"),
    "fiber_g": ("Ballaststoffe", "Fiber"),
    "sugar_g": ("Zucker", "Sugar"),
    "sodium_mg": ("Natrium (mg)", "Sodium (mg)"),
}


class MfpImportError(ValueError):
    """The upload is not a usable MFP export. The message is safe to show to the user."""


@dataclass
class Parsed:
    meals: dict[tuple[date, str], dict]
    weights: dict[date, Decimal]
    ignored: list[str]


def _number(value: str | None, where: str) -> Decimal | None:
    value = (value or "").strip().replace(",", ".")
    if not value:
        return None
    try:
        return Decimal(value)
    except InvalidOperation:
        raise MfpImportError(f"{where}: {value!r} is not a number") from None


def _day(value: str | None, where: str) -> date:
    try:
        return date.fromisoformat((value or "").strip())
    except ValueError:
        raise MfpImportError(f"{where}: unreadable date {value!r}") from None


def _column(fields: list[str], names: tuple[str, ...]) -> str | None:
    return next((n for n in names if n in fields), None)


def _parse_csv(name: str, data: bytes, out: Parsed) -> None:
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise MfpImportError(f"{name}: not UTF-8 text") from None
    reader = csv.DictReader(io.StringIO(text))
    fields = reader.fieldnames or []
    date_col = _column(fields, ("Datum", "Date"))
    meal_col = _column(fields, ("Mahlzeit", "Meal"))
    weight_col = _column(fields, ("Gewicht", "Weight"))

    if "Workout name" in fields or "Exercise" in fields:
        # Has "Date" and "Weight" too; without this check its sets would become body weights.
        raise MfpImportError(f"{name}: this is a Gym Day export, import it in the Training tab")
    if date_col and meal_col:
        columns = {f: _column(fields, names) for f, names in NUTRITION_COLUMNS.items()}
        if columns["kcal"] is None:
            raise MfpImportError(f"{name}: nutrition file without a calories column")
        for line, row in enumerate(reader, start=2):
            where = f"{name}, line {line}"
            day = _day(row[date_col], where)
            label = (row[meal_col] or "").strip()
            values = {f: _number(row[c], where) if c else None for f, c in columns.items()}
            if values["kcal"] is None:
                continue
            out.meals[(day, MEALS.get(label.lower(), "unknown"))] = {
                **values,
                "raw": {k: v for k, v in row.items() if k},
            }
    elif date_col and weight_col:
        for line, row in enumerate(reader, start=2):
            where = f"{name}, line {line}"
            kg = _number(row[weight_col], where)
            if kg is not None:
                out.weights[_day(row[date_col], where)] = kg
    elif "Training" in fields or "Exercise" in fields:
        out.ignored.append(name)
    else:
        raise MfpImportError(f"{name}: not a MyFitnessPal nutrition or weight export")


def parse(data: bytes, filename: str = "export.csv") -> Parsed:
    if len(data) > MAX_BYTES:
        raise MfpImportError("file is larger than 10 MB")
    out = Parsed(meals={}, weights={}, ignored=[])
    if data[:2] == b"PK":
        try:
            archive = zipfile.ZipFile(io.BytesIO(data))
        except zipfile.BadZipFile:
            raise MfpImportError("broken zip file") from None
        csvs = [i for i in archive.infolist() if i.filename.lower().endswith(".csv")]
        if not csvs:
            raise MfpImportError("the zip contains no CSV files")
        for info in csvs:
            if info.file_size > MAX_BYTES:
                raise MfpImportError(f"{info.filename}: larger than 10 MB")
            _parse_csv(info.filename.rsplit("/", 1)[-1], archive.read(info), out)
    else:
        _parse_csv(filename, data, out)
    if not out.meals and not out.weights:
        raise MfpImportError("the export contains no nutrition or weight values")
    return out


def import_export(session: Session, data: bytes, filename: str = "export.csv") -> dict:
    parsed = parse(data, filename)
    days = {d for d, _ in parsed.meals} | set(parsed.weights)

    existing = {
        (m.local_date, m.meal): m
        for m in session.scalars(
            select(NutritionMeal).where(
                NutritionMeal.source == SOURCE, NutritionMeal.local_date.in_(days)
            )
        )
    }
    created = updated = unchanged = 0
    for (day, meal), values in parsed.meals.items():
        row = existing.get((day, meal))
        if row is None:
            session.add(NutritionMeal(source=SOURCE, local_date=day, meal=meal, **values))
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
                BodyWeight.source == SOURCE, BodyWeight.local_date.in_(set(parsed.weights))
            )
        )
    }
    weights_created = 0
    for day, kg in parsed.weights.items():
        row = weights.get(day)
        if row is None:
            session.add(BodyWeight(source=SOURCE, local_date=day, kg=kg))
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
    integrations.record_success(session, "mfp_export", stats)
    return stats
