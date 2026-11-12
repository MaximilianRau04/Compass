from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select

from app.config import get_settings
from app.ingestion import health_auto_export, healthconnect
from app.models.health import DailyMetrics, HealthRecord, HeartRateSample, SleepSession
from app.models.nutrition import BodyWeight, NutritionMeal
from app.services import health
from app.services.clock import local_today

BERLIN = ZoneInfo("Europe/Berlin")
TOKEN = "test-token-0123456789"
WATCH = "Apple Watch von Maxi"
URL = "/api/ingest/health-auto-export"


def at(day, hhmm: str) -> datetime:
    h, m = map(int, hhmm.split(":"))
    return datetime(day.year, day.month, day.day, h, m, tzinfo=BERLIN)


def hae(value: datetime) -> str:
    """A time as Health Auto Export writes it: '2026-11-11 23:00:00 +0100'."""
    return value.astimezone(BERLIN).strftime("%Y-%m-%d %H:%M:%S %z")


def export(*metrics, workouts=()) -> dict:
    return {"data": {"metrics": list(metrics), "workouts": list(workouts)}}


def metric(name, units, *points) -> dict:
    return {"name": name, "units": units, "data": list(points)}


def segment(start: datetime, minutes: int, value: str, source=WATCH) -> dict:
    end = start + timedelta(minutes=minutes)
    return {
        "date": hae(start),
        "start": hae(start),
        "end": hae(end),
        "startDate": hae(start),
        "endDate": hae(end),
        "qty": minutes / 60,
        "value": value,
        "source": source,
    }


def night_segments(wake_day, source=WATCH) -> list[dict]:
    """In bed 22:45 to 07:00, from 23:00: 150 core, 60 deep, 15 awake, 90 REM, 150 core."""
    bed = at(wake_day - timedelta(days=1), "22:45")
    out = [segment(bed, 495, "In Bed", source)]
    cursor = at(wake_day - timedelta(days=1), "23:00")
    for value, minutes in [("Core", 150), ("Deep", 60), ("Awake", 15), ("REM", 90), ("Core", 150)]:
        out.append(segment(cursor, minutes, value, source))
        cursor += timedelta(minutes=minutes)
    return out


def ingest(session, body: dict) -> dict:
    converted = health_auto_export.convert(session, health_auto_export.Export.model_validate(body))
    for payload in health_auto_export.batches(converted, None):
        healthconnect.ingest(session, payload)
    session.flush()
    return {"skipped": converted.skipped, "unknown": converted.unknown}


@pytest.fixture
def token(monkeypatch):
    monkeypatch.setattr(get_settings(), "health_token", TOKEN)
    return {"Authorization": f"Bearer {TOKEN}"}


def test_time_format_of_the_app_is_parsed():
    parsed = health_auto_export.parse_time("2024-02-06 14:30:00 -0800")
    assert parsed is not None and parsed.utcoffset() == timedelta(hours=-8)
    assert health_auto_export.parse_time("2024-02-06T14:30:00+01:00") is not None
    assert health_auto_export.parse_time("2024-02-06 14:30:00") is None


def test_endpoint_needs_the_token(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "health_token", "")
    monkeypatch.setattr(get_settings(), "healthconnect_token", "")
    response = client.post(URL, json=export())
    assert response.status_code == 503
    assert "HEALTH_TOKEN" in response.json()["detail"]


def test_endpoint_rejects_wrong_token(client, token):
    assert (
        client.post(URL, json=export(), headers={"Authorization": "Bearer no"}).status_code == 401
    )


def test_old_token_name_still_works(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "health_token", "")
    monkeypatch.setattr(get_settings(), "healthconnect_token", TOKEN)
    headers = {"Authorization": f"Bearer {TOKEN}"}
    assert client.post(URL, json=export(), headers=headers).status_code == 200
    assert client.get("/api/ingest/health", headers=headers).status_code == 200
    assert client.get("/api/ingest/healthconnect", headers=headers).status_code == 200


def test_endpoint_stores_steps_and_reports_unknown_metrics(client, token, session):
    day = local_today()
    body = export(
        metric("step_count", "count", {"qty": 800, "date": hae(at(day, "09:00")), "source": WATCH}),
        metric("step_count", "count", {"qty": 400, "date": hae(at(day, "10:00")), "source": WATCH}),
        metric("toothbrushing", "s", {"qty": 120, "date": hae(at(day, "07:00"))}),
    )
    response = client.post(URL, json=body, headers={**token, "automation-name": "Compass"})
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["created"] == 2
    assert result["unknown"] == ["toothbrushing"]
    assert session.get(DailyMetrics, day).steps == 1200
    again = client.post(URL, json=body, headers=token).json()
    assert again["created"] == 0 and again["unchanged"] == 2


def test_heart_rate_weight_and_extras(session):
    day = local_today()
    ingest(
        session,
        export(
            metric(
                "heart_rate",
                "count/min",
                {"date": hae(at(day, "08:00")), "Min": 60, "Avg": 64.4, "Max": 70, "source": WATCH},
                {"date": hae(at(day, "08:05")), "Min": 70, "Avg": 80, "Max": 90, "source": WATCH},
            ),
            metric("resting_heart_rate", "count/min", {"qty": 52, "date": hae(at(day, "07:00"))}),
            metric("weight_body_mass", "lb", {"qty": 176.4, "date": hae(at(day, "07:10"))}),
            metric("heart_rate_variability", "ms", {"qty": 48, "date": hae(at(day, "06:00"))}),
            metric("blood_oxygen_saturation", "%", {"qty": 0.97, "date": hae(at(day, "06:00"))}),
            metric("walking_running_distance", "km", {"qty": 2.5, "date": hae(at(day, "09:00"))}),
        ),
    )
    assert sorted(s.bpm for s in session.scalars(select(HeartRateSample))) == [64, 80]
    metrics = session.get(DailyMetrics, day)
    assert metrics.resting_hr == 52
    assert (metrics.hr_min, metrics.hr_max) == (64, 80)
    weight = session.scalar(select(BodyWeight).where(BodyWeight.local_date == day))
    assert float(weight.kg) == pytest.approx(80.01, abs=0.01)
    extras = health.extras(session, day, day)[day]
    assert extras["heart_rate_variability_sdnn"] == 48
    assert "heart_rate_variability" not in extras
    assert extras["oxygen_saturation"] == 97
    assert extras["distance"] == 2500


def test_energy_counts_active_plus_basal_as_burned(session):
    day = local_today()
    ingest(
        session,
        export(
            metric("active_energy", "kJ", {"qty": 2092, "date": hae(at(day, "10:00"))}),
            metric("basal_energy_burned", "kcal", {"qty": 1600, "date": hae(at(day, "10:00"))}),
        ),
    )
    assert session.get(DailyMetrics, day).kcal_burned == 2100
    assert health.extras(session, day, day)[day]["active_calories"] == 500


def test_sleep_phases_become_a_night_for_the_wake_day(session):
    day = local_today()
    ingest(session, export(metric("sleep_analysis", "hr", *night_segments(day))))
    sleep = session.scalar(select(SleepSession))
    assert sleep.local_date == day
    assert sleep.in_bed_minutes == 495
    # 15 awake, plus 15 in bed before falling asleep and 15 after waking up.
    assert sleep.awake_minutes == 45
    assert (sleep.deep_minutes, sleep.light_minutes, sleep.rem_minutes) == (60, 300, 90)
    assert sleep.asleep_minutes == 450


def test_a_night_in_two_exports_is_merged(session):
    day = local_today()
    segments = night_segments(day)
    ingest(session, export(metric("sleep_analysis", "hr", *segments[:3])))
    ingest(session, export(metric("sleep_analysis", "hr", *segments[3:])))
    nights = list(session.scalars(select(SleepSession)))
    assert len(nights) == 1
    assert nights[0].rem_minutes == 90 and nights[0].deep_minutes == 60
    assert nights[0].in_bed_minutes == 495


def test_two_nights_and_two_sources_stay_apart(session):
    day = local_today()
    ingest(
        session,
        export(
            metric(
                "sleep_analysis",
                "hr",
                *night_segments(day),
                *night_segments(day - timedelta(days=1)),
                *night_segments(day, source="iPhone"),
            )
        ),
    )
    assert len(list(session.scalars(select(SleepSession)))) == 3
    assert session.get(DailyMetrics, day).sleep_minutes == 450


def test_summarized_sleep_counts_without_phases(session):
    day = local_today()
    point = {
        "date": hae(at(day, "00:00")),
        "totalSleep": 7.5,
        "sleepStart": hae(at(day - timedelta(days=1), "23:00")),
        "sleepEnd": hae(at(day, "06:30")),
        "inBedStart": hae(at(day - timedelta(days=1), "22:45")),
        "inBedEnd": hae(at(day, "06:45")),
        "source": WATCH,
    }
    ingest(session, export(metric("sleep_analysis", "hr", point)))
    sleep = session.scalar(select(SleepSession))
    assert sleep.local_date == day and sleep.asleep_minutes == 450
    assert sleep.deep_minutes is None


def test_nutrition_sums_into_one_meal_of_the_app_with_most_calories(session):
    day = local_today()

    def food(qty, name, hhmm="12:30", source="MyFitnessPal"):
        when = at(day, hhmm)
        return {
            "date": hae(when),
            "start": hae(when),
            "end": hae(when),
            "qty": qty,
            "source": source,
            "foodType": name,
        }

    ingest(
        session,
        export(
            metric(
                "dietary_energy",
                "kcal",
                food(400, "Pasta"),
                food(200, "Salad"),
                food(100, "Apple", source="Lose It!"),
            ),
            metric("protein", "g", food(15, "Pasta"), food(3, "Salad")),
            metric("sodium", "g", food(1.2, "Pasta")),
        ),
    )
    meals = list(session.scalars(select(NutritionMeal).where(NutritionMeal.local_date == day)))
    assert len(meals) == 1
    assert float(meals[0].kcal) == 600 and float(meals[0].protein_g) == 18
    assert meals[0].raw == {"app": "MyFitnessPal"}


def test_workouts_become_exercise_records(session):
    day = local_today()
    workouts = [
        {
            "id": "550e8400-e29b-41d4-a716-446655440000",
            "name": "Traditional Strength Training",
            "start": hae(at(day, "17:00")),
            "end": hae(at(day, "18:10")),
            "duration": 4200,
            "source": {"name": "Workout", "identifier": "com.apple.workout"},
        },
        {"name": "Running", "start": hae(at(day, "07:00")), "duration": 1800, "isIndoor": True},
        {"name": "Golf", "start": hae(at(day, "12:00")), "end": hae(at(day, "14:00"))},
    ]
    ingest(session, export(workouts=workouts))
    rows = {r.raw["data"]["exercise"]: r for r in session.scalars(select(HealthRecord))}
    assert set(rows) == {"strength_training", "running_treadmill", "golf"}
    assert rows["strength_training"].id == "hae:workout:550e8400-e29b-41d4-a716-446655440000"
    assert rows["strength_training"].source_app == "Workout"
    assert rows["running_treadmill"].end_at - rows["running_treadmill"].start_at == timedelta(
        minutes=30
    )


def test_readings_without_time_or_value_are_skipped(session):
    result = ingest(
        session,
        export(
            metric("step_count", "count", {"qty": 5}, {"date": "yesterday", "qty": 5}),
            metric(
                "weight_body_mass",
                "stone-ish",
                {"qty": 80, "date": hae(at(local_today(), "07:00"))},
            ),
        ),
    )
    assert result["skipped"] == 3
    assert session.scalar(select(HealthRecord)) is None
