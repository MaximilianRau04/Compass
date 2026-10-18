import json
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select

from app.config import get_settings
from app.ingestion import gymday, healthconnect
from app.models.health import DailyMetrics, HealthRecord, HeartRateSample, SleepSession
from app.models.training import TrainingSession
from app.schemas.health import IngestPayload
from app.services.clock import local_today

UTC = ZoneInfo("UTC")
BERLIN = ZoneInfo("Europe/Berlin")
ZEPP = "com.huami.watch.hmwatchmanager"
GYMDAY = "com.anthonyng.workoutapp"
TOKEN = "test-token-0123456789"


def at(day, hhmm: str) -> datetime:
    """Local Berlin time on a day, as UTC (what the app sends)."""
    h, m = map(int, hhmm.split(":"))
    return datetime(day.year, day.month, day.day, h, m, tzinfo=BERLIN).astimezone(UTC)


def iso(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def record(id, type, start, end=None, source=ZEPP, **data) -> dict:
    out = {"id": id, "type": type, "source": source, "start": iso(start), "data": data}
    if end is not None:
        out["end"] = iso(end)
    return out


def night(id="sleep-1", wake_day=None, source=ZEPP) -> dict:
    """23:00 to 07:00: 60 deep, 300 light, 90 REM, 30 awake."""
    wake_day = wake_day or local_today()
    bed = at(wake_day - timedelta(days=1), "23:00")
    stages, cursor = [], bed
    for stage, minutes in [
        ("light", 150),
        ("deep", 60),
        ("awake", 30),
        ("rem", 90),
        ("light", 150),
    ]:
        stages.append(
            {"start": iso(cursor), "end": iso(cursor + timedelta(minutes=minutes)), "stage": stage}
        )
        cursor += timedelta(minutes=minutes)
    return record(id, "sleep", bed, cursor, source=source, stages=stages)


def ingest(session, records=(), deleted=()):
    payload = IngestPayload.model_validate({"records": list(records), "deleted": list(deleted)})
    return healthconnect.ingest(session, payload)


@pytest.fixture
def token(monkeypatch):
    monkeypatch.setattr(get_settings(), "healthconnect_token", TOKEN)
    return {"Authorization": f"Bearer {TOKEN}"}


def test_endpoint_needs_configured_token(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "healthconnect_token", "")
    assert client.post("/api/ingest/healthconnect", json={}).status_code == 503


def test_endpoint_rejects_wrong_token(client, token):
    response = client.post(
        "/api/ingest/healthconnect", json={}, headers={"Authorization": "Bearer nope"}
    )
    assert response.status_code == 401
    assert client.get("/api/ingest/healthconnect").status_code == 401


def test_endpoint_ingests_and_reports_status(client, token):
    response = client.post(
        "/api/ingest/healthconnect",
        json={"device": "SM-A556B", "app_version": "0.1.0", "records": [night()]},
        headers=token,
    )
    assert response.status_code == 200, response.text
    assert response.json()["created"] == 1
    status = client.get("/api/ingest/healthconnect", headers=token).json()
    assert status["ok"] is True
    assert status["last_success_at"] is not None


def test_endpoint_rejects_naive_timestamps(client, token):
    bad = {"id": "x", "type": "steps", "start": "2026-10-17T10:00:00", "data": {"count": 5}}
    response = client.post("/api/ingest/healthconnect", json={"records": [bad]}, headers=token)
    assert response.status_code == 422


def test_sleep_is_split_into_stages_and_counts_for_the_wake_day(session):
    today = local_today()
    stats = ingest(session, [night()])
    assert stats["created"] == 1
    sleep = session.scalar(select(SleepSession))
    assert sleep.local_date == today
    assert sleep.in_bed_minutes == 480
    assert sleep.asleep_minutes == 450
    assert (sleep.deep_minutes, sleep.light_minutes, sleep.rem_minutes, sleep.awake_minutes) == (
        60,
        300,
        90,
        30,
    )
    assert len(sleep.stages) == 5
    assert session.get(DailyMetrics, today).sleep_minutes == 450


def test_sleep_without_stages_counts_the_whole_session(session):
    today = local_today()
    ingest(session, [record("s", "sleep", at(today, "01:00"), at(today, "06:30"))])
    sleep = session.scalar(select(SleepSession))
    assert sleep.asleep_minutes == 330
    assert sleep.deep_minutes is None and sleep.awake_minutes is None


def test_ingest_is_idempotent_and_applies_edits(session):
    ingest(session, [night()])
    again = ingest(session, [night()])
    assert (again["created"], again["updated"], again["unchanged"]) == (0, 0, 1)

    edited = night()
    edited["data"]["stages"] = edited["data"]["stages"][:2]  # only the first 210 minutes
    edited["end"] = edited["data"]["stages"][-1]["end"]
    stats = ingest(session, [edited])
    assert stats["updated"] == 1
    sleep = session.scalar(select(SleepSession))
    assert sleep.in_bed_minutes == 210
    assert session.scalar(select(SleepSession.id).where(SleepSession.id != sleep.id)) is None


def test_deletion_removes_derived_data_and_stays_deleted(session):
    today = local_today()
    ingest(session, [night()])
    stats = ingest(session, deleted=["sleep-1", "never-seen"])
    assert stats["deleted"] == 1
    assert session.scalar(select(SleepSession)) is None
    assert session.get(DailyMetrics, today) is None
    assert session.get(HealthRecord, "sleep-1").deleted_at is not None
    # A late copy of the same record does not bring it back.
    assert ingest(session, [night()])["unchanged"] == 1
    assert session.scalar(select(SleepSession)) is None


def test_steps_from_two_apps_are_not_added_up(session):
    today = local_today()
    ingest(
        session,
        [
            record("z1", "steps", at(today, "08:00"), at(today, "09:00"), count=3000),
            record("z2", "steps", at(today, "12:00"), at(today, "13:00"), count=2500),
            record(
                "s1",
                "steps",
                at(today, "08:00"),
                at(today, "13:00"),
                source="com.sec.android.app.shealth",
                count=5200,
            ),
            record("c1", "total_calories", at(today, "00:00"), at(today, "12:00"), kcal=1450.6),
        ],
    )
    metrics = session.get(DailyMetrics, today)
    assert metrics.steps == 5500
    assert metrics.steps_source == ZEPP
    assert metrics.kcal_burned == 1451


def test_heart_rate_samples_and_resting_rate(session):
    today = local_today()
    start = at(today, "10:00")
    samples = [
        {"time": iso(start + timedelta(minutes=i)), "bpm": bpm}
        for i, bpm in enumerate([60, 90, 120])
    ]
    ingest(
        session,
        [
            record("hr", "heart_rate", start, start + timedelta(minutes=3), samples=samples),
            record("rhr", "resting_heart_rate", at(today, "07:00"), bpm=52),
        ],
    )
    metrics = session.get(DailyMetrics, today)
    assert (metrics.hr_min, metrics.hr_avg, metrics.hr_max, metrics.resting_hr) == (60, 90, 120, 52)

    # Sending the record again with other samples replaces them.
    ingest(session, [record("hr", "heart_rate", start, start, samples=samples[:1])])
    assert len(list(session.scalars(select(HeartRateSample)))) == 1
    assert session.get(DailyMetrics, today).hr_max == 60


def test_bad_derived_data_keeps_the_record_and_the_sync_going(session):
    today = local_today()
    stats = ingest(
        session,
        [
            record("bad", "heart_rate", at(today, "10:00"), samples=[{"time": "soon", "bpm": 0}]),
            record("ok", "steps", at(today, "10:00"), at(today, "11:00"), count=100),
        ],
    )
    assert stats["invalid"] == 1
    assert session.get(HealthRecord, "bad") is not None
    assert session.get(DailyMetrics, today).steps == 100


def test_unknown_types_are_stored_raw(session):
    today = local_today()
    ingest(
        session,
        [
            record(
                "meal",
                "nutrition",
                at(today, "08:00"),
                at(today, "08:15"),
                source="com.myfitnesspal.android",
                meal_type="breakfast",
                energy_kcal=650,
                protein_g=40,
            )
        ],
    )
    row = session.get(HealthRecord, "meal")
    assert row.raw["data"]["protein_g"] == 40
    assert row.local_date == today


def gymday_csv(when_local: str) -> bytes:
    header = (
        '"Date","Workout name","Exercise","Set","Weight","Reps","Distance","Duration",'
        '"Measurement unit","Notes"'
    )
    row = f'"{when_local}","Pull","Latzug","1","70","10","","","kg",'
    return f"{header}\n{row}\n".encode()


def test_gymday_duration_from_health_connect_either_order(session):
    day = local_today() - timedelta(days=2)
    # Health Connect first, then the CSV import.
    ingest(
        session,
        [
            record(
                "gd",
                "exercise",
                at(day, "17:55"),
                at(day, "19:10"),
                source=GYMDAY,
                exercise="strength_training",
            )
        ],
    )
    gymday.import_csv(session, gymday_csv(f"{day:%Y-%m-%d} 18:01:00"))
    training = session.scalar(select(TrainingSession))
    assert training.duration_minutes == 75
    assert training.health_record_id == "gd"

    # The Gym Day entry is deleted in Health Connect: the duration goes away again.
    ingest(session, deleted=["gd"])
    assert training.duration_minutes is None

    # CSV first, then a new Health Connect entry.
    ingest(session, [record("gd2", "exercise", at(day, "17:50"), at(day, "19:00"), source=GYMDAY)])
    assert training.duration_minutes == 70


def test_gymday_match_ignores_other_apps_and_far_sessions(session):
    day = local_today() - timedelta(days=1)
    gymday.import_csv(session, gymday_csv(f"{day:%Y-%m-%d} 18:00:00"))
    ingest(
        session,
        [
            record(
                "zepp", "exercise", at(day, "17:58"), at(day, "19:00"), exercise="strength_training"
            ),
            record("morning", "exercise", at(day, "07:00"), at(day, "08:00"), source=GYMDAY),
        ],
    )
    assert session.scalar(select(TrainingSession)).duration_minutes is None


def test_summary_endpoint(client, session):
    today = local_today()
    bed = at(today - timedelta(days=1), "23:00")
    samples = [{"time": iso(bed + timedelta(minutes=i)), "bpm": 50 + i} for i in range(10)]
    ingest(
        session,
        [
            night(),
            record("hr", "heart_rate", bed, bed + timedelta(minutes=10), samples=samples),
            record("st", "steps", at(today, "09:00"), at(today, "10:00"), count=4000),
            record(
                "run",
                "exercise",
                at(today, "07:30"),
                at(today, "08:10"),
                exercise="running",
                title="Lauf",
            ),
        ],
    )
    data = client.get("/api/sleep/summary?days=7").json()
    last = data["last_night"]
    assert last["asleep_minutes"] == 450
    assert [s["stage"] for s in last["stages"]] == ["light", "deep", "awake", "rem", "light"]
    assert [p["bpm"] for p in last["heart_rate"]] == [52, 57]  # 5-minute averages
    assert len(data["nights"]) == 1
    day = next(d for d in data["days"] if d["date"] == today.isoformat())
    assert day["steps"] == 4000
    assert data["averages"]["sleep_minutes"] == 450
    assert data["workouts"] == [
        {
            "id": "run",
            "source_app": ZEPP,
            "start_at": data["workouts"][0]["start_at"],
            "end_at": data["workouts"][0]["end_at"],
            "duration_minutes": 40,
            "title": "Lauf",
            "exercise": "running",
            "gymday_duplicate": False,
        }
    ]
    detail = client.get(f"/api/sleep/nights/{last['id']}").json()
    assert detail["deep_minutes"] == 60


def test_zepp_workout_during_gymday_session_is_a_duplicate(session):
    from app.services import health

    day = local_today()
    gymday.import_csv(session, gymday_csv(f"{day:%Y-%m-%d} 18:00:00"))
    ingest(session, [record("zepp", "exercise", at(day, "17:58"), at(day, "19:00"))])
    [workout] = health.workouts(session, day, day)
    assert workout.gymday_duplicate is True


def test_bridge_app_output_is_accepted(session):
    """The JSON the Android app produces for every type (written by its HealthTypesTest)."""
    records = json.loads(
        (Path(__file__).parent / "fixtures/healthconnect_records.json").read_text()
    )
    stats = ingest(session, records)
    assert stats["created"] == len(records) == 8
    assert stats["invalid"] == 0
    sleep = session.scalar(select(SleepSession).where(SleepSession.record_id == "sleep-1"))
    assert (sleep.light_minutes, sleep.deep_minutes) == (60, 420)
    assert session.get(HealthRecord, "meal-1").raw["data"]["meal_type"] == "breakfast"
