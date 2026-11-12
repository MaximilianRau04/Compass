"""The records of the iOS bridge (ios/), as its core writes them: the Swift test
ios/Core/Tests/BridgeCoreTests/ContractTests.swift checks that its output equals this fixture."""

import json
from datetime import date
from pathlib import Path

from sqlalchemy import select

from app.ingestion import healthconnect
from app.models.health import DailyMetrics, HealthRecord, SleepSession
from app.models.nutrition import BodyWeight, NutritionMeal
from app.schemas.health import IngestPayload
from app.services import health

FIXTURE = Path(__file__).parent / "fixtures" / "healthkit_records.json"
DAY = date(2026, 10, 18)


def test_healthkit_records_are_ingested(session):
    records = json.loads(FIXTURE.read_text())
    stats = healthconnect.ingest(
        session, IngestPayload.model_validate({"device": "iPhone", "records": records})
    )
    assert stats["created"] == len(records)
    assert stats["invalid"] == 0

    sleep = session.scalar(select(SleepSession))
    assert sleep.local_date == DAY
    assert (sleep.deep_minutes, sleep.light_minutes, sleep.rem_minutes) == (60, 300, 90)
    assert sleep.awake_minutes == 45

    metrics = session.get(DailyMetrics, DAY)
    assert metrics.resting_hr == 52
    assert metrics.kcal_burned == 1900  # active 300 plus basal 1600
    assert session.get(DailyMetrics, date(2026, 10, 17)).steps == 1234

    extras = health.extras(session, DAY, DAY)[DAY]
    assert extras["heart_rate_variability_sdnn"] == 48.5
    assert extras["oxygen_saturation"] == 97
    assert extras["active_calories"] == 300

    meal = session.scalar(select(NutritionMeal).where(NutritionMeal.local_date == DAY))
    assert float(meal.kcal) == 650 and float(meal.protein_g) == 40
    weight = session.scalar(select(BodyWeight).where(BodyWeight.local_date == DAY))
    assert float(weight.kg) == 78.7
    workout = session.scalar(select(HealthRecord).where(HealthRecord.type == "exercise"))
    assert workout.raw["data"]["exercise"] == "strength_training"


def test_a_snapshot_with_a_prefix_leaves_other_bridges_alone(session):
    night = json.loads(FIXTURE.read_text())[0]
    android = {**night, "id": "android-night", "source": "com.huami.watch.hmwatchmanager"}
    healthconnect.ingest(session, IngestPayload.model_validate({"records": [night, android]}))
    # The iPhone no longer has its night; the Android night must stay.
    snapshot = {"type": "sleep", "since": "2026-10-17T00:00:00Z", "ids": [], "prefix": "hk:sleep:"}
    stats = healthconnect.ingest(session, IngestPayload.model_validate({"snapshots": [snapshot]}))
    assert stats["deleted"] == 1
    alive = session.scalars(select(HealthRecord.id).where(HealthRecord.deleted_at.is_(None)))
    assert list(alive) == ["android-night"]
