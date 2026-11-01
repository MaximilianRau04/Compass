import io
import zipfile
from datetime import timedelta
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.ingestion import nutrition_export
from app.models.nutrition import BodyWeight, NutritionMeal
from app.services import nutrition
from app.services.clock import local_today
from tests.test_healthconnect import at, ingest, record

MFP = "com.myfitnesspal.android"
NUTRITION_HEADER = (
    "Datum,Mahlzeit,Kalorien,Fett (g),Gesättigte Fettsäuren,Mehrfach ungesättigte Fettsäuren,"
    "Einfach ungesättigte Fettsäuren,Transfettsäuren,Cholesterin,Natrium (mg),Kalium,"
    "Kohlenhydrate (g),Ballaststoffe,Zucker,Eiweiß (g),Vitamin A,Vitamin C,Kalzium,Eisen,"
    "export_headers.note"
)


def meal_row(day, meal, kcal, fat=10.0, carbs=50.0, protein=30.0) -> str:
    # Fat, saturated, poly, mono, trans, cholesterol, sodium, potassium; carbs, fiber, sugar,
    # protein; vitamins and minerals; the empty note column.
    middle = f"{fat},2.0,0.0,0.0,0.0,0.0,500.0,0.0,{carbs},5.0,8.0,{protein}"
    return f"{day},{meal},{kcal},{middle},0,0,0,0,"


def nutrition_csv(*rows: str) -> bytes:
    return ("﻿" + "\n".join([NUTRITION_HEADER, *rows]) + "\n").encode()


def weight_csv(*rows: tuple[str, str]) -> bytes:
    return ("Datum,Gewicht\n" + "".join(f"{d},{kg}\n" for d, kg in rows)).encode()


def zipped(files: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, data in files.items():
            archive.writestr(name, data)
    return buffer.getvalue()


def count(session, model) -> int:
    return session.scalar(select(func.count()).select_from(model))


def hc_meal(id, day, meal_type, kcal, protein=None, source=MFP, hhmm="08:00"):
    data = {"meal_type": meal_type, "energy_kcal": kcal}
    if protein is not None:
        data["protein_g"] = protein
    return record(id, "nutrition", at(day, hhmm), at(day, hhmm), source=source, **data)


def test_export_import_maps_meals_and_is_idempotent(session):
    data = nutrition_csv(
        meal_row("2022-07-11", "Frühstück", 935.1, protein=27.6),
        meal_row("2022-07-11", "Abendessen", 406.8, protein=16.8),
        meal_row("2022-07-12", "Snacks", 200),
    )
    stats = nutrition_export.import_export(session, data)
    assert (stats["meals_created"], stats["days"], stats["first"]) == (3, 2, "2022-07-11")
    breakfast = session.scalar(select(NutritionMeal).where(NutritionMeal.meal == "breakfast"))
    assert breakfast.kcal == Decimal("935.1")
    assert breakfast.protein_g == Decimal("27.6")
    assert breakfast.sodium_mg == Decimal("500.0")
    assert breakfast.raw["Mahlzeit"] == "Frühstück"

    again = nutrition_export.import_export(session, data)
    assert (again["meals_created"], again["meals_unchanged"]) == (0, 3)
    changed = nutrition_export.import_export(
        session, nutrition_csv(meal_row("2022-07-12", "Snacks", 250))
    )
    assert changed["meals_updated"] == 1
    assert count(session, NutritionMeal) == 3


def test_zip_with_all_three_files(session):
    data = zipped(
        {
            "Dateiexport/Nährwerte-Übersicht-2022-07-11-bis-2026-10-16.csv": nutrition_csv(
                meal_row("2026-10-01", "Mittagessen", 800)
            ),
            "Dateiexport/Messwerte-Übersicht-2022-07-11-bis-2026-10-16.csv": weight_csv(
                ("2026-10-01", "78.7"), ("2026-10-06", "78.4")
            ),
            "Dateiexport/Trainingsübersicht-2022-07-11-bis-2026-10-16.csv": (
                b"Datum,Training,Typ,Kalorien aus Training\n2026-09-16,Strength,Ausdauer,318.0\n"
            ),
        }
    )
    stats = nutrition_export.import_export(session, data)
    assert stats["meals_created"] == 1
    assert stats["weights_created"] == 2
    assert stats["ignored_files"] == ["Trainingsübersicht-2022-07-11-bis-2026-10-16.csv"]
    assert [w.kg for w in nutrition.weights(session)] == [78.7, 78.4]


def test_import_endpoint_rejects_other_files(client):
    gymday = (
        b'"Date","Workout name","Exercise","Set","Weight","Reps"\n'
        b'"2026-10-01 18:00:00","Pull","Latzug","1","70","10"\n'
    )
    response = client.post("/api/nutrition/import", content=gymday)
    assert response.status_code == 422
    assert "workout export" in response.json()["detail"]

    other = client.post("/api/nutrition/import", content=b"a,b\n1,2\n")
    assert "not a nutrition export" in other.json()["detail"]

    ok = client.post("/api/nutrition/import", content=weight_csv(("2026-10-06", "78.7")))
    assert ok.status_code == 200, ok.text
    assert ok.json()["weights_created"] == 1


def test_healthconnect_meals_are_summed_per_meal(session):
    today = local_today()
    ingest(
        session,
        [
            hc_meal("m1", today, "breakfast", 400, protein=30),
            hc_meal("m2", today, "breakfast", 250.5, protein=10, hhmm="08:05"),
            hc_meal("m3", today, "dinner", 900),
        ],
    )
    [day] = nutrition.days(session, today, today)
    assert day.source == "healthconnect"
    assert [(m.meal, m.kcal, m.protein_g) for m in day.meals] == [
        ("breakfast", 650.5, 40.0),
        ("dinner", 900.0, None),
    ]
    assert day.kcal == 1550.5
    assert day.protein_g == 40.0

    # A meal deleted in MFP disappears again.
    ingest(session, deleted=["m3"])
    [day] = nutrition.days(session, today, today)
    assert [m.meal for m in day.meals] == ["breakfast"]


def test_two_apps_do_not_add_up(session):
    today = local_today()
    ingest(
        session,
        [
            hc_meal("a", today, "lunch", 800),
            hc_meal("b", today, "lunch", 750, source="com.other.tracker"),
        ],
    )
    [day] = nutrition.days(session, today, today)
    assert day.kcal == 800


def test_healthconnect_wins_over_the_export_per_day(session):
    today = local_today()
    yesterday = today - timedelta(days=1)
    nutrition_export.import_export(
        session,
        nutrition_csv(
            meal_row(yesterday.isoformat(), "Frühstück", 500),
            meal_row(today.isoformat(), "Frühstück", 500),
        ),
    )
    ingest(session, [hc_meal("m", today, "breakfast", 620)])
    days = nutrition.days(session, yesterday, today)
    assert [(d.date, d.source, d.kcal) for d in days] == [
        (yesterday, "mfp_export", 500.0),
        (today, "healthconnect", 620.0),
    ]


def test_healthconnect_weight_takes_the_morning_weigh_in(session):
    """The earliest weigh-in of the day: morning weights compare from day to day."""
    today = local_today()
    nutrition_export.import_export(session, weight_csv((today.isoformat(), "80.0")))
    ingest(
        session,
        [
            record("w1", "weight", at(today, "07:00"), kg=78.9),
            record("w2", "weight", at(today, "21:00"), kg=79.6),
        ],
    )
    assert [(w.kg, w.source) for w in nutrition.weights(session)] == [(78.9, "healthconnect")]
    assert count(session, BodyWeight) == 2  # the export row stays, it just loses


def test_goals_apply_from_their_day(client, session):
    today = local_today()
    assert client.put("/api/nutrition/goals/protein_g", json={"value": 160}).status_code == 200
    earlier = (today - timedelta(days=10)).isoformat()
    client.put("/api/nutrition/goals/protein_g", json={"value": 140, "valid_from": earlier})
    assert nutrition.goals_on(session, today) == {"protein_g": 160.0}
    assert nutrition.goals_on(session, today - timedelta(days=5)) == {"protein_g": 140.0}
    assert nutrition.goals_on(session, today - timedelta(days=20)) == {}

    assert client.put("/api/nutrition/goals/water", json={"value": 1}).status_code == 422
    assert client.put("/api/nutrition/goals/kcal", json={"value": 0}).status_code == 422
    history = client.get("/api/nutrition/goals").json()
    assert [(g["metric"], g["value"]) for g in history] == [("protein_g", 160), ("protein_g", 140)]


def test_summary_excludes_today_and_counts_goal_days(client, session):
    today = local_today()
    rows = [
        meal_row((today - timedelta(days=n)).isoformat(), "Mittagessen", kcal, protein=protein)
        for n, kcal, protein in [(1, 2400, 180), (2, 2600, 150), (4, 2500, 175)]
    ]
    nutrition_export.import_export(session, nutrition_csv(*rows))
    nutrition_export.import_export(
        session,
        weight_csv(((today - timedelta(days=6)).isoformat(), "79.0"), (today.isoformat(), "78.4")),
    )
    ingest(session, [hc_meal("now", today, "breakfast", 300, protein=20)])
    nutrition.set_goal(session, "protein_g", 170, today - timedelta(days=30))
    nutrition.set_goal(session, "kcal", 2500, today - timedelta(days=30))

    data = client.get("/api/nutrition/summary?days=7").json()
    assert [d["kcal"] for d in data["days"]] == [2500, 2600, 2400, 300]
    assert data["averages"]["kcal"] == 2500  # today (300 so far) is not complete yet
    assert data["averages"]["protein_g"] == pytest.approx(168.3, abs=0.1)
    assert data["protein_goal_days"] == 2
    assert data["goals"] == {"kcal": 2500, "protein_g": 170}
    assert data["weight"]["kg"] == 78.4
    assert data["weight_change"] == -0.6
    assert sum(w["days_tracked"] for w in data["weeks"]) == 4
    assert data["days"][-1]["meals"] == [
        {"meal": "breakfast", "kcal": 300, "protein_g": 20, "carbs_g": None, "fat_g": None}
    ]


def test_real_export_if_present(session):
    """Runs against the real export in data/ when it is there (it is not committed)."""
    from pathlib import Path

    folder = Path(__file__).parents[2] / "data" / "Dateiexport-2022-07-11-bis-2026-10-16"
    files = sorted(folder.glob("*.csv")) if folder.exists() else []
    if not files:
        pytest.skip("MFP export not present")
    data = zipped({f.name: f.read_bytes() for f in files})
    stats = nutrition_export.import_export(session, data)
    assert stats["meals_created"] == 3098
    assert stats["days"] == 785
    assert stats["weights_created"] == 433
    assert len(stats["ignored_files"]) == 1


def lunch(id, day, kcal, **extra):
    return record(
        id,
        "nutrition",
        at(day, "12:00"),
        at(day, "12:30"),
        meal_type="lunch",
        energy_kcal=kcal,
        protein_g=100,
        **extra,
    )


def test_minerals_from_health_connect(session):
    today = local_today()
    ingest(
        session,
        [lunch("m1", today, 2000, potassium_mg=3500, calcium_mg=900, iron_mg=12, fiber_g=30)],
    )
    [day] = nutrition.days(session, today, today)
    assert (day.potassium_mg, day.calcium_mg, day.iron_mg, day.fiber_g) == (3500, 900, 12, 30)


def test_quality_flags_and_averages(client, session):
    today = local_today()
    d = lambda n: today - timedelta(days=n)  # noqa: E731
    ingest(
        session,
        [
            lunch("a", d(5), 2400),
            lunch("b", d(4), 2400),  # same totals as the day before
            lunch("c", d(3), 900),  # incomplete
            lunch("e", d(1), 2000),
            lunch("t", today, 500),  # today is still running: never flagged
        ],
    )
    s = nutrition.summary(session, 7)
    assert s.quality.same_as_previous_day == [d(4)]
    assert s.quality.incomplete == [d(3)]
    assert s.quality.gaps == [d(6), d(2)]
    assert s.quality.valid_days == 2
    assert s.averages["kcal"] == 2200  # 2400 and 2000 only
    assert s.averages_all["kcal"] == pytest.approx((2400 + 2400 + 900 + 2000) / 4, abs=0.1)
    flags = {day.date: day.flags for day in s.days}
    assert flags[today] == [] and flags[d(3)] == ["incomplete"]

    data = client.get("/api/nutrition/summary?days=7").json()
    assert data["quality"]["valid_days"] == 2 and data["averages"]["kcal"] == 2200


CRONOMETER = (
    "Day,Time,Group,Food Name,Amount,Energy (kcal),Carbs (g),Fat (g),Protein (g),Sodium (mg)\n"
    "2026-10-05,8:00 AM,Breakfast,Oats,50.00 g,190.123,32.5,3.4,6.7,2.0\n"
    "2026-10-05,8:05 AM,Breakfast,Milk,200.00 ml,92.456,9.6,3.0,6.6,88.0\n"
    "2026-10-05,,Total,,,282.579,42.1,6.4,13.3,90.0\n"
    "2026-10-05,1:00 PM,Uncategorized,Apple,1.00 x,52.0,14.0,,0.3,\n"
)
LOSE_IT = (
    "Date,Name,Icon,Meal,Quantity,Units,Calories,Deleted,Fat (g),Protein (g),Carbohydrates (g),"
    "Saturated Fat (g),Sugars (g),Fiber (g),Cholesterol (mg),Sodium (mg)\n"
    "10/05/2026,Greek Yogurt,Yogurt,Breakfast,1,cup,120,false,0,20,8,0,6,0,10,60\n"
    "10/05/2026,Banana,Banana,Breakfast,1,each,105,false,0.4,1.3,27,n/a,14,3.1,0,1\n"
    "10/05/2026,Cake,Cake,Snacks,1,slice,400,true,20,4,50,10,30,1,50,200\n"
)


def meals_of(session, source):
    rows = session.scalars(select(NutritionMeal).where(NutritionMeal.source == source)).all()
    return {r.meal: r for r in rows}


def test_cronometer_foods_are_summed_per_meal_without_its_totals(session):
    stats = nutrition_export.import_export(session, CRONOMETER.encode())
    assert (stats["meals_created"], stats["days"]) == (2, 1)
    meals = meals_of(session, "cronometer_export")
    assert set(meals) == {"breakfast", "unknown"}
    assert meals["breakfast"].kcal == Decimal("282.6")
    assert meals["breakfast"].protein_g == Decimal("13.3")
    assert meals["breakfast"].sodium_mg == Decimal("90.0")
    # An empty cell stays unknown, it does not become 0.
    assert meals["unknown"].fat_g is None


def test_importing_a_food_app_again_changes_nothing(session):
    nutrition_export.import_export(session, CRONOMETER.encode())
    session.expire_all()
    again = nutrition_export.import_export(session, CRONOMETER.encode())
    assert (again["meals_created"], again["meals_updated"]) == (0, 0)
    assert again["meals_unchanged"] == 2


def test_cronometer_weight_is_converted_by_its_unit(session):
    data = (
        "Day,Group,Metric,Unit,Amount\n"
        "2026-10-05,Morning,Weight,lbs,176.37\n"
        "2026-10-06,Morning,Weight,kg,79.5\n"
        "2026-10-06,Morning,Blood Pressure,mmHg,120/80\n"
    )
    stats = nutrition_export.import_export(session, data.encode())
    assert stats["weights_created"] == 2
    rows = session.scalars(select(BodyWeight).order_by(BodyWeight.local_date)).all()
    assert [r.kg for r in rows] == [Decimal("80.00"), Decimal("79.50")]
    assert {r.source for r in rows} == {"cronometer_export"}


def test_an_unknown_weight_unit_is_refused(session):
    data = "Day,Metric,Unit,Amount\n2026-10-05,Weight,stone,12\n"
    with pytest.raises(nutrition_export.NutritionImportError, match="unknown unit"):
        nutrition_export.import_export(session, data.encode())


def test_lose_it_is_not_mistaken_for_myfitnesspal(session):
    assert nutrition_export.parse(LOSE_IT.encode()).source == "loseit_export"


def test_lose_it_leaves_out_deleted_entries(session):
    stats = nutrition_export.import_export(session, LOSE_IT.encode())
    assert (stats["first"], stats["days"]) == ("2026-10-05", 1)
    meals = meals_of(session, "loseit_export")
    assert set(meals) == {"breakfast"}
    assert meals["breakfast"].kcal == Decimal("225.0")
    assert meals["breakfast"].fiber_g == Decimal("3.1")
    # "n/a" in one row and 0 in the other: the sum of what is known.
    assert meals["breakfast"].saturated_fat_g == Decimal("0.0")


def test_lose_it_zip_takes_the_food_log_and_leaves_out_weights_without_a_unit(session):
    weights = b"Date,Weight,Deleted\n10/05/2026,180,false\n"
    data = zipped(
        {
            "weights.csv": weights,
            "food-logs.csv": LOSE_IT.encode(),
            "daily-calorie-summary.csv": b"Date,Food cals,Exercise cals,Budget cals,EER\n",
        }
    )
    stats = nutrition_export.import_export(session, data)
    assert stats["weights_created"] == 0
    assert sorted(stats["ignored_files"]) == ["daily-calorie-summary.csv", "weights.csv"]
    assert session.scalars(select(BodyWeight)).all() == []


def test_lose_it_weights_alone_explain_why_they_are_refused(session):
    weights = b"Date,Weight,Deleted\n10/05/2026,180,false\n"
    with pytest.raises(nutrition_export.NutritionImportError, match="name no unit"):
        nutrition_export.import_export(session, weights)


def test_a_zip_cannot_mix_two_apps(session):
    data = zipped({"a.csv": CRONOMETER.encode(), "b.csv": LOSE_IT.encode()})
    with pytest.raises(nutrition_export.NutritionImportError, match="different apps"):
        nutrition_export.import_export(session, data)


def test_a_workout_file_in_a_zip_is_left_out(session):
    data = zipped(
        {
            "nutrition.csv": nutrition_csv(meal_row("2026-10-05", "Lunch", 700)),
            "exercise.csv": b"Date,Exercise,Type\n2026-10-05,Running,Cardio\n",
        }
    )
    stats = nutrition_export.import_export(session, data)
    assert stats["ignored_files"] == ["exercise.csv"]
    assert stats["meals_created"] == 1


def test_health_connect_beats_an_export_of_any_app(session):
    today = local_today()
    data = CRONOMETER.replace("2026-10-05", today.isoformat()).encode()
    nutrition_export.import_export(session, data)
    ingest(session, [hc_meal("h1", today, "lunch", 700)])
    found = nutrition.days(session, today, today)
    assert [(d.source, d.kcal) for d in found] == [("healthconnect", 700.0)]


def test_every_format_counts_for_the_days_and_weights():
    assert {f.source for f in nutrition_export.FORMATS} <= set(nutrition.SOURCES)
