from datetime import datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import func, select

from app.ingestion import workouts
from app.models.training import Exercise, ExerciseSet, TrainingSession
from app.services import training
from app.services.clock import local_today

HEADER = (
    '"Date","Workout name","Exercise","Set","Weight","Reps","Distance","Duration",'
    '"Measurement unit","Notes"'
)


def row(when: str, workout: str, exercise: str, set_no: int, weight: str, reps: int) -> str:
    return f'"{when}","{workout}","{exercise}","{set_no}","{weight}","{reps}","","","kg",'


def export(*rows: str) -> bytes:
    # Gym Day writes a UTF-8 BOM.
    return ("﻿" + "\n".join([HEADER, *rows]) + "\n").encode()


def recent(days_ago: int, hhmm: str = "18:00") -> str:
    return f"{local_today() - timedelta(days=days_ago):%Y-%m-%d} {hhmm}:00"


SAMPLE = export(
    row("2025-09-04 20:15:30", "Push A", "Supine Press", 1, "60", 10),
    row("2025-09-04 20:15:30", "Push A", "Supine Press", 2, "55", 9),
    row("2025-09-04 20:15:30", "Push A", "Trizeps Dips", 1, "", 12),
    row("2025-09-06 10:30:00", "Pull", "Latzug mit engem Griff", 1, "70", 10),
)


def count(session, model) -> int:
    return session.scalar(select(func.count()).select_from(model))


def test_import_creates_sessions_sets_and_exercises(session):
    stats = workouts.import_csv(session, SAMPLE)
    assert stats == {
        "rows": 4,
        "sessions_created": 2,
        "sets_created": 4,
        "sets_updated": 0,
        "sets_unchanged": 0,
        "exercises_created": 3,
        "first": "2025-09-04",
        "last": "2025-09-06",
    }
    push = session.scalar(select(TrainingSession).where(TrainingSession.workout_name == "Push A"))
    # Local time without zone in the file; stored as UTC (CEST is UTC+2).
    assert push.started_at == datetime(2025, 9, 4, 18, 15, 30, tzinfo=ZoneInfo("UTC"))

    dips = session.scalar(select(Exercise).where(Exercise.name == "Trizeps Dips"))
    assert dips.bodyweight is True
    dip_set = session.scalar(select(ExerciseSet).where(ExerciseSet.exercise_id == dips.id))
    assert dip_set.weight_kg is None  # bodyweight, not 0 kg
    assert dip_set.raw["Exercise"] == "Trizeps Dips"
    press = session.scalar(select(Exercise).where(Exercise.name == "Supine Press"))
    assert press.bodyweight is False
    assert [a.alias for a in press.aliases] == ["Supine Press"]


def test_import_is_idempotent_and_updates_changed_sets(session):
    workouts.import_csv(session, SAMPLE)
    again = workouts.import_csv(session, SAMPLE)
    assert again["sessions_created"] == 0
    assert again["sets_created"] == 0
    assert again["sets_unchanged"] == 4
    assert count(session, ExerciseSet) == 4

    corrected = export(
        row("2025-09-04 20:15:30", "Push A", "Supine Press", 2, "57.5", 8),
        row("2025-09-08 19:00:00", "Leg", "Beinstrecken", 1, "60", 12),
    )
    stats = workouts.import_csv(session, corrected)
    assert stats["sets_updated"] == 1
    assert stats["sets_created"] == 1
    assert stats["sessions_created"] == 1
    second = session.scalar(select(ExerciseSet).where(ExerciseSet.weight_kg == Decimal("57.5")))
    assert second.reps == 8


def test_import_rejects_other_files(client):
    response = client.post("/api/training/import", content=b"name,amount\nfoo,1\n")
    assert response.status_code == 422
    assert "not a workout export" in response.json()["detail"]

    broken = export('"yesterday","Push","Bench","1","50","x","","","kg",')
    response = client.post("/api/training/import", content=broken)
    assert response.status_code == 422
    assert "line 2" in response.json()["detail"]


def test_import_through_the_api(client):
    response = client.post(
        "/api/training/import", content=SAMPLE, headers={"Content-Type": "text/csv"}
    )
    assert response.status_code == 200, response.text
    assert response.json()["sets_created"] == 4
    names = [e["name"] for e in client.get("/api/training/exercises").json()]
    assert set(names) == {"Supine Press", "Trizeps Dips", "Latzug mit engem Griff"}


def test_e1rm_and_split():
    assert training.e1rm(Decimal("100"), 10) == pytest.approx(133.3)
    assert training.e1rm(Decimal("100"), 1) == 100
    assert training.e1rm(None, 10) is None  # bodyweight
    assert training.e1rm(Decimal("40"), 20) is None  # too many reps for an estimate
    assert [training.split_of(n) for n in ("Push B", "Pull", "Leg day", "Beine", "Arme")] == [
        "push",
        "pull",
        "legs",
        "legs",
        "other",
    ]


def test_summary_counts_weeks_volume_and_split(client, session):
    workouts.import_csv(
        session,
        export(
            row(recent(0), "Push A", "Supine Press", 1, "100", 10),
            row(recent(0), "Push A", "Supine Press", 2, "100", 8),
            row(recent(0), "Push A", "Trizeps Dips", 1, "", 12),
            row(recent(7, "17:00"), "Pull", "Latzug mit engem Griff", 1, "70", 10),
            row(recent(400), "Leg", "Beinstrecken", 1, "60", 12),
        ),
    )
    summary = client.get("/api/training/summary", params={"weeks": 4}).json()
    assert len(summary["weeks"]) == 4
    assert summary["sessions"] == 2  # the old leg day is outside the range
    assert summary["this_week_sessions"] == 1
    assert summary["weeks"][-1]["volume_kg"] == 1800  # dips are bodyweight, not counted
    assert summary["split"] == {"push": 1, "pull": 1, "legs": 0, "other": 0, "sport": 0}
    assert summary["last_session"]["workout_name"] == "Push A"
    assert summary["last_session"]["exercises"] == 2

    sessions = client.get("/api/training/sessions").json()
    assert [s["workout_name"] for s in sessions] == ["Push A", "Pull", "Leg"]
    detail = client.get(f"/api/training/sessions/{sessions[0]['id']}").json()
    press = next(e for e in detail["exercise_sets"] if e["name"] == "Supine Press")
    assert [s["set_index"] for s in press["sets"]] == [1, 2]
    assert press["sets"][0]["e1rm"] == pytest.approx(133.3)


def test_progress_per_session(client, session):
    workouts.import_csv(
        session,
        export(
            row(recent(14), "Pull", "Latzug mit engem Griff", 1, "65", 10),
            row(recent(14), "Pull", "Latzug mit engem Griff", 2, "65", 9),
            row(recent(7), "Pull", "Latzug mit engem Griff", 1, "70", 10),
        ),
    )
    exercise = session.scalar(select(Exercise).where(Exercise.name == "Latzug mit engem Griff"))
    points = client.get(f"/api/training/exercises/{exercise.id}/progress").json()
    assert [p["top_weight"] for p in points] == [65, 70]
    assert [p["sets"] for p in points] == [2, 1]
    assert points[0]["volume_kg"] == 65 * 10 + 65 * 9
    assert points[1]["best_e1rm"] > points[0]["best_e1rm"]


def test_rename_in_gymday_and_merge(client, session):
    workouts.import_csv(session, export(row(recent(10), "Pull", "Latzug eng", 1, "60", 10)))
    workouts.import_csv(
        session, export(row(recent(3), "Pull", "Latzug mit engem Griff", 1, "65", 10))
    )
    old = session.scalar(select(Exercise).where(Exercise.name == "Latzug eng"))
    new = session.scalar(select(Exercise).where(Exercise.name == "Latzug mit engem Griff"))

    merged = client.post(f"/api/training/exercises/{old.id}/merge", json={"into": new.id})
    assert merged.status_code == 200, merged.text
    assert merged.json()["aliases"] == ["Latzug eng", "Latzug mit engem Griff"]
    assert merged.json()["sessions"] == 2
    assert session.get(Exercise, old.id) is None

    # A later export with the old name lands on the merged exercise.
    stats = workouts.import_csv(session, export(row(recent(1), "Pull", "Latzug eng", 1, "67.5", 9)))
    assert stats["exercises_created"] == 0
    progress = client.get(f"/api/training/exercises/{new.id}/progress").json()
    assert [p["top_weight"] for p in progress] == [60, 65, 67.5]


def test_merge_refuses_overlapping_sets(client, session):
    workouts.import_csv(
        session,
        export(
            row(recent(2), "Push", "Butterfly", 1, "50", 10),
            row(recent(2), "Push", "Flys am Kabel", 1, "20", 12),
        ),
    )
    a = session.scalar(select(Exercise).where(Exercise.name == "Butterfly"))
    b = session.scalar(select(Exercise).where(Exercise.name == "Flys am Kabel"))
    response = client.post(f"/api/training/exercises/{a.id}/merge", json={"into": b.id})
    assert response.status_code == 409


def test_update_exercise(client, session):
    workouts.import_csv(session, SAMPLE)
    press = session.scalar(select(Exercise).where(Exercise.name == "Supine Press"))
    response = client.patch(
        f"/api/training/exercises/{press.id}",
        json={"name": "Bankdrücken liegend", "muscle_group": "Brust"},
    )
    assert response.status_code == 200
    assert response.json()["muscle_group"] == "Brust"
    # The export name stays as an alias, so the next import still finds the exercise.
    assert response.json()["aliases"] == ["Supine Press"]
    assert workouts.import_csv(session, SAMPLE)["exercises_created"] == 0

    taken = client.patch(
        f"/api/training/exercises/{press.id}", json={"name": "Latzug mit engem Griff"}
    )
    assert taken.status_code == 409


def test_find_exercise_by_part_of_the_name(session):
    workouts.import_csv(
        session,
        export(
            row(recent(1), "Leg", "Beinpresse einbeinig", 1, "80", 10),
            row(recent(1), "Leg", "Wadenheben an der Beinpresse", 1, "100", 15),
            row(recent(1), "Pull", "Latzug mit engem Griff", 1, "70", 10),
        ),
    )
    assert training.find_exercise(session, "latzug").name == "Latzug mit engem Griff"
    assert training.find_exercise(session, "Beinpresse einbeinig").name == "Beinpresse einbeinig"
    with pytest.raises(training.TrainingError, match="several"):
        training.find_exercise(session, "beinpresse")
    with pytest.raises(training.TrainingError, match="No exercise"):
        training.find_exercise(session, "Kreuzheben")


# --- Other apps ----------------------------------------------------------------------------------

STRONG = (
    b"Date,Workout Name,Duration,Exercise Name,Set Order,Weight,Reps,Distance,Seconds,Notes,"
    b"Workout Notes,RPE\n"
    b"2026-09-01 18:00:00,Push,1h 5m,Bench Press,W,40,10,0,0,,,\n"
    b"2026-09-01 18:00:00,Push,1h 5m,Bench Press,1,60,10,0,0,,,8\n"
    b"2026-09-01 18:00:00,Push,1h 5m,Bench Press,2,60,9,0,0,,,\n"
    b"2026-09-01 18:00:00,Push,1h 5m,Dips,1,0,12,0,0,,,\n"
    b"2026-09-01 18:00:00,Push,1h 5m,Bench Press,1,50,12,0,0,,,\n"
    b"2026-09-01 18:00:00,Push,1h 5m,Rowing,1,0,0,500,120,,,\n"
)
HEVY = (
    b"title,start_time,end_time,description,exercise_title,superset_id,exercise_notes,set_index,"
    b"set_type,weight_kg,reps,distance_km,duration_seconds,rpe\n"
    b'Pull,"1 Sep 2026, 18:00","1 Sep 2026, 19:10",,Barbell Row,,,0,warmup,40,10,,,\n'
    b'Pull,"1 Sep 2026, 18:00","1 Sep 2026, 19:10",,Barbell Row,,,1,normal,70,8,,,\n'
    b'Pull,"1 Sep 2026, 18:00","1 Sep 2026, 19:10",,Pull Up,,,0,normal,,10,,,\n'
)


def sets_of(session, exercise):
    rows = session.scalars(
        select(ExerciseSet).join(Exercise).where(Exercise.name == exercise)
    ).all()
    return sorted((s.set_index, s.weight_kg, s.reps) for s in rows)


def test_strong_export(session):
    stats = workouts.import_csv(session, STRONG)
    assert stats["sessions_created"] == 1
    s = session.scalar(select(TrainingSession))
    assert (s.source, s.workout_name, s.duration_minutes) == ("strong", "Push", 65)
    # Without the warm-up; the exercise done twice keeps all its sets; 0 kg is bodyweight.
    assert sets_of(session, "Bench Press") == [
        (1, Decimal("60.00"), 10),
        (2, Decimal("60.00"), 9),
        (3, Decimal("50.00"), 12),
    ]
    assert sets_of(session, "Dips") == [(1, None, 12)]
    assert sets_of(session, "Rowing") == []
    again = workouts.import_csv(session, STRONG)
    assert (again["sets_created"], again["sessions_created"]) == (0, 0)


def test_strong_export_with_semicolons_and_pounds(session):
    data = (
        b"Date;Workout Name;Duration (sec);Exercise Name;Set Order;Weight (lbs);Reps\n"
        b"2026-09-01 18:00:00;Push;3600;Bench Press;1;100;10\n"
    )
    workouts.import_csv(session, data)
    assert sets_of(session, "Bench Press") == [(1, Decimal("45.36"), 10)]
    assert session.scalar(select(TrainingSession)).duration_minutes == 60


def test_hevy_export(session):
    workouts.import_csv(session, HEVY)
    s = session.scalar(select(TrainingSession))
    assert (s.source, s.workout_name, s.duration_minutes) == ("hevy", "Pull", 70)
    assert sets_of(session, "Barbell Row") == [(1, Decimal("70.00"), 8)]
    assert sets_of(session, "Pull Up") == [(1, None, 10)]
    assert workouts.import_csv(session, HEVY)["sets_created"] == 0
