import json
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select

from app.config import get_settings
from app.ingestion import healthconnect, workouts
from app.models.health import DailyMetrics, HealthRecord, HeartRateSample, SleepSession
from app.models.nutrition import BodyWeight, NutritionMeal
from app.models.training import TrainingSession
from app.schemas.health import IngestPayload
from app.services import health
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


def ingest(session, records=(), deleted=(), snapshots=()):
    payload = IngestPayload.model_validate(
        {"records": list(records), "deleted": list(deleted), "snapshots": list(snapshots)}
    )
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
    # Counted back from the end, so the night of a clock change has the same length.
    end = at(today, "06:30")
    ingest(session, [record("s", "sleep", end - timedelta(minutes=330), end)])
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


def test_deletion_removes_derived_data(session):
    today = local_today()
    ingest(session, [night()])
    stats = ingest(session, deleted=["sleep-1", "never-seen"])
    assert stats["deleted"] == 1
    assert session.scalar(select(SleepSession)) is None
    assert session.get(DailyMetrics, today) is None
    assert session.get(HealthRecord, "sleep-1").deleted_at is not None
    assert ingest(session, deleted=["sleep-1"])["deleted"] == 0


def test_rewritten_record_with_the_same_id_comes_back(session):
    """Zepp deletes a night and writes it again; Health Connect keeps the id. Seen on 20.10.2026:
    the upsert came in the first request, the deletion and the new upsert in the second."""
    today = local_today()
    ingest(session, [night()])
    ingest(session, deleted=["sleep-1"])
    stats = ingest(session, [night()])
    assert (stats["restored"], stats["unchanged"]) == (1, 0)
    assert session.get(HealthRecord, "sleep-1").deleted_at is None
    assert session.scalar(select(SleepSession)).local_date == today
    assert session.get(DailyMetrics, today).sleep_minutes is not None


def test_record_wins_over_a_deletion_in_the_same_batch(session):
    today = local_today()
    ingest(session, [night()])
    stats = ingest(session, [night()], deleted=["sleep-1"])
    assert stats["deleted"] == 0
    assert session.get(HealthRecord, "sleep-1").deleted_at is None
    assert session.scalar(select(SleepSession)).local_date == today
    # The same in the first batch of a new record.
    ingest(session, [night(id="sleep-2")], deleted=["sleep-2"])
    assert session.get(HealthRecord, "sleep-2").deleted_at is None


def test_snapshot_adds_the_missing_version_and_drops_stale_ones(session):
    """21.10.2026: Zepp wrote the night three times under new ids; the change feed delivered the
    first two (and their deletions) but never the last one."""
    today = local_today()
    since = at(today - timedelta(days=3), "00:00").isoformat()
    ingest(session, [night("v1")])
    ingest(session, [night("v2")], deleted=["v1"])
    old = night("old", wake_day=today - timedelta(days=5))
    ingest(session, [old])

    final = night("v3")
    stats = ingest(session, [final], snapshots=[{"type": "sleep", "since": since, "ids": ["v3"]}])
    assert stats["created"] == 1 and stats["deleted"] == 1  # v2 is gone from Health Connect
    alive = session.scalars(select(HealthRecord.id).where(HealthRecord.deleted_at.is_(None)))
    assert set(alive) == {"v3", "old"}  # older than the snapshot range: untouched
    assert {s.record_id for s in session.scalars(select(SleepSession))} == {"v3", "old"}
    assert session.get(DailyMetrics, today).sleep_minutes is not None

    # A snapshot only touches its own type.
    ingest(session, [record("st", "steps", at(today, "08:00"), at(today, "09:00"), count=10)])
    ingest(session, snapshots=[{"type": "sleep", "since": since, "ids": ["v3"]}])
    assert session.get(HealthRecord, "st").deleted_at is None


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
    workouts.import_csv(session, gymday_csv(f"{day:%Y-%m-%d} 18:01:00"))
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
    workouts.import_csv(session, gymday_csv(f"{day:%Y-%m-%d} 18:00:00"))
    ingest(
        session,
        [
            record(
                "zepp", "exercise", at(day, "17:58"), at(day, "19:00"), exercise="strength_training"
            ),
            record("morning", "exercise", at(day, "07:00"), at(day, "08:00"), source=GYMDAY),
        ],
    )
    csv_session = session.scalar(select(TrainingSession).where(TrainingSession.source == "gymday"))
    # No Gym Day entry for it in Health Connect, so the watch gives the duration; the Zepp
    # workout is not a session of its own.
    assert (csv_session.watch_record_id, csv_session.duration_minutes) == ("zepp", 62)
    assert session.scalar(select(TrainingSession).where(TrainingSession.source == "watch")) is None
    # The far Gym Day entry is a session of its own (without sets), not the CSV one's duration.
    [extra] = session.scalars(
        select(TrainingSession).where(TrainingSession.source == "healthconnect")
    ).all()
    assert (extra.health_record_id, extra.duration_minutes) == ("morning", 60)


def test_gymday_sessions_without_export_become_sessions_without_sets(client, session):
    day = local_today() - timedelta(days=1)
    ingest(
        session,
        [
            record(
                "gd", "exercise", at(day, "18:00"), at(day, "19:05"), source=GYMDAY, title="Leg"
            ),
            record("zepp", "exercise", at(day, "17:58"), at(day, "19:00")),
        ],
    )
    [placeholder] = session.scalars(select(TrainingSession)).all()
    assert (placeholder.source, placeholder.workout_name) == ("healthconnect", "Leg")
    assert placeholder.duration_minutes == 65

    sessions = client.get("/api/training/sessions").json()
    assert [(s["workout_name"], s["split"], s["sets"], s["source"]) for s in sessions] == [
        ("Leg", "legs", 0, "healthconnect")
    ]
    summary = client.get("/api/training/summary?weeks=4").json()
    assert summary["sessions"] == 1
    assert summary["split"]["legs"] == 1
    # The Zepp recording of the same session is still a duplicate, not a second training.
    [zepp] = health.workouts(session, day, day)
    assert zepp.gymday_duplicate is True

    # Sending the record again does not create a second placeholder.
    ingest(
        session,
        [record("gd", "exercise", at(day, "18:00"), at(day, "19:10"), source=GYMDAY, title="Leg")],
    )
    [placeholder] = session.scalars(select(TrainingSession)).all()
    assert placeholder.duration_minutes == 70

    # The CSV with the sets arrives later: it takes over, nothing is duplicated.
    workouts.import_csv(session, gymday_csv(f"{day:%Y-%m-%d} 18:00:00"))
    [training] = session.scalars(select(TrainingSession)).all()
    assert (training.source, training.health_record_id, training.duration_minutes) == (
        "gymday",
        "gd",
        70,
    )
    assert len(training.sets) == 1


def test_deleted_gymday_entry_removes_its_placeholder(session):
    day = local_today()
    ingest(session, [record("gd", "exercise", at(day, "18:00"), at(day, "19:00"), source=GYMDAY)])
    assert session.scalar(select(TrainingSession)).workout_name == "Training"  # no title
    ingest(session, deleted=["gd"])
    assert session.scalar(select(TrainingSession)) is None


def test_rebuild_derives_records_stored_before_a_release(session):
    """Records that arrived before meals or placeholders were derived get them from the CLI."""
    from app.cli import rebuild_health
    from app.services import nutrition

    day = local_today() - timedelta(days=2)
    for r in [
        record("gd", "exercise", at(day, "18:00"), at(day, "19:00"), source=GYMDAY, title="Pull"),
        record(
            "meal",
            "nutrition",
            at(day, "12:00"),
            at(day, "12:00"),
            meal_type="lunch",
            energy_kcal=800,
        ),
        record("st", "steps", at(day, "10:00"), at(day, "11:00"), count=5000),
    ]:
        parsed = IngestPayload.model_validate({"records": [r]}).records[0]
        session.add(
            HealthRecord(
                id=parsed.id,
                type=parsed.type,
                source_app=parsed.source,
                start_at=parsed.start,
                end_at=parsed.end or parsed.start,
                local_date=healthconnect.local_day(parsed),
                raw=parsed.model_dump(mode="json"),
            )
        )
    session.flush()

    assert rebuild_health(session) == {"days": 1, "gymday_sessions": 1, "watch_workouts": 0}
    assert session.scalar(select(TrainingSession)).workout_name == "Pull"
    assert nutrition.days(session, day, day)[0].kcal == 800
    assert session.get(DailyMetrics, day).steps == 5000
    # Running it again changes nothing.
    assert rebuild_health(session) == {"days": 1, "gymday_sessions": 1, "watch_workouts": 0}
    assert len(session.scalars(select(TrainingSession)).all()) == 1


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
    day = local_today()
    workouts.import_csv(session, gymday_csv(f"{day:%Y-%m-%d} 18:00:00"))
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
    meal = session.scalar(select(NutritionMeal).where(NutritionMeal.source == "healthconnect"))
    assert (meal.meal, meal.kcal, meal.protein_g) == ("breakfast", 650, 40)
    weight = session.scalar(select(BodyWeight).where(BodyWeight.source == "healthconnect"))
    assert float(weight.kg) == 78.7


def test_day_heart_rate_endpoint(client, session):
    today = local_today()
    morning = at(today, "08:00")
    samples = [{"time": iso(morning + timedelta(minutes=i)), "bpm": 60 + i} for i in range(12)]
    ingest(
        session,
        [
            night(),
            record("hr", "heart_rate", morning, morning + timedelta(minutes=12), samples=samples),
            record("rhr", "resting_heart_rate", at(today, "07:00"), bpm=52),
        ],
    )
    data = client.get("/api/sleep/heart-rate").json()
    assert data["date"] == today.isoformat()
    assert [p["bpm"] for p in data["points"]] == [62, 67, 71]  # 5-minute averages, rounded
    assert (data["min"], data["max"], data["resting"]) == (60, 71, 52)
    assert data["last"]["bpm"] == 71
    assert data["sleep_end"] is not None
    empty = client.get("/api/sleep/heart-rate", params={"day": "2020-01-01"}).json()
    assert empty["points"] == [] and empty["last"] is None and empty["sleep_start"] is None


def test_extra_metrics_in_the_summary(client, session):
    today = local_today()
    ingest(
        session,
        [
            record("o1", "oxygen_saturation", at(today, "03:00"), percent=96.0),
            record("o2", "oxygen_saturation", at(today, "04:00"), percent=98.0),
            record("d1", "distance", at(today, "09:00"), at(today, "10:00"), meters=1200.0),
            record("d2", "distance", at(today, "11:00"), at(today, "12:00"), meters=800.0),
            record("v1", "heart_rate_variability", at(today, "05:00"), rmssd_ms=42.0),
        ],
    )
    extras = client.get("/api/sleep/summary?days=7").json()["extras"]
    assert extras == [
        {
            "date": today.isoformat(),
            "oxygen_saturation": 97.0,
            "heart_rate_variability": 42.0,
            "heart_rate_variability_sdnn": None,
            "respiratory_rate": None,
            "distance": 2000.0,
            "active_calories": None,
        }
    ]


def hr(id, start, minutes, bpm):
    samples = [{"time": iso(start + timedelta(minutes=i)), "bpm": bpm + i} for i in range(minutes)]
    return record(id, "heart_rate", start, start + timedelta(minutes=minutes), samples=samples)


def test_watch_workout_without_gymday_becomes_a_session(client, session):
    """Bouldering tracked with Zepp only: a session of its own, with the watch's heart rate."""
    day = local_today() - timedelta(days=1)
    start = at(day, "18:00")
    ingest(
        session,
        [
            record("climb", "exercise", start, at(day, "19:30"), exercise="rock_climbing"),
            hr("hr1", start, 10, 100),
        ],
    )
    [s] = session.scalars(select(TrainingSession)).all()
    assert (s.source, s.workout_name, s.activity, s.duration_minutes) == (
        "watch",
        "Climbing",
        "rock_climbing",
        90,
    )
    assert (s.hr_avg, s.hr_max) == (105, 109)
    summary = client.get("/api/training/summary?weeks=2").json()
    assert summary["split"]["sport"] == 1
    assert summary["last_session"]["hr_max"] == 109

    # Heart rate that arrives in a later sync is added to the session.
    ingest(session, [hr("hr2", start + timedelta(minutes=30), 5, 150)])
    assert session.get(TrainingSession, s.id).hr_max == 154

    # Deleted in Health Connect: the session goes too.
    ingest(session, deleted=["climb"])
    assert session.scalars(select(TrainingSession)).all() == []


def test_watch_strength_workout_enriches_the_gymday_session(session):
    day = local_today() - timedelta(days=1)
    workouts.import_csv(session, gymday_csv(f"{day:%Y-%m-%d} 18:00:00"))
    ingest(
        session,
        [
            record("gd", "exercise", at(day, "18:00"), at(day, "19:05"), source=GYMDAY),
            record(
                "zepp", "exercise", at(day, "17:58"), at(day, "19:02"), exercise="strength_training"
            ),
            hr("hr1", at(day, "18:10"), 20, 110),
        ],
    )
    sessions = session.scalars(select(TrainingSession)).all()
    assert [s.source for s in sessions] == ["gymday"]  # no duplicate from Zepp
    [s] = sessions
    assert (s.health_record_id, s.watch_record_id, s.duration_minutes) == ("gd", "zepp", 65)
    assert (s.hr_avg, s.hr_max) == (120, 129)


def test_old_exercise_type_numbers_get_their_name(session):
    """App versions before 0.2.1 sent unknown types as "type_<n>", bouldering as type_51."""
    day = local_today() - timedelta(days=1)
    ingest(
        session,
        [
            record(
                "climb",
                "exercise",
                at(day, "18:00"),
                at(day, "19:00"),
                exercise="type_51",
                exercise_type=51,
            )
        ],
    )
    s = session.scalar(select(TrainingSession))
    assert (s.workout_name, s.activity) == ("Climbing", "rock_climbing")
