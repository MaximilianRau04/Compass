import uuid
from contextlib import nullcontext
from datetime import datetime, timedelta

import pytest
from mcp import Client
from sqlalchemy import select

from app.mcp import db as mcp_db
from app.mcp.server import mcp
from app.models.training import Exercise, ExerciseSet, TrainingSession
from app.services import progression, workout_log
from app.services.clock import local_today, local_tz
from app.services.workout_log import LoggedSession


def at(days_ago: int, hhmm: str = "18:00") -> datetime:
    day = local_today() - timedelta(days=days_ago)
    h, m = map(int, hhmm.split(":"))
    return datetime(day.year, day.month, day.day, h, m, tzinfo=local_tz())


def logged(name="Push A", days_ago=0, exercises=None, ended=True, client_id=None):
    start = at(days_ago)
    return LoggedSession.model_validate(
        {
            "client_id": client_id or str(uuid.uuid4()),
            "workout_name": name,
            "started_at": start.isoformat(),
            "ended_at": (start + timedelta(minutes=70)).isoformat() if ended else None,
            "exercises": exercises
            or [{"name": "Bankdrücken", "sets": [{"weight_kg": 60, "reps": 10, "rir": 2}]}],
        }
    )


def bench(*sets):
    return [
        {
            "name": "Bankdrücken",
            "sets": [dict(zip(("weight_kg", "reps", "rir"), s, strict=True)) for s in sets],
        }
    ]


def test_saving_again_updates_the_same_session(session):
    first = logged(ended=False)
    t = workout_log.save(session, first)
    assert (t.source, t.duration_minutes) == ("compass", None)
    again = first.model_copy(
        update={
            "ended_at": first.started_at + timedelta(minutes=65),
            "exercises": logged(exercises=bench((60, 10, 2), (60, 9, 1))).exercises,
        }
    )
    t2 = workout_log.save(session, again)
    assert t2.id == t.id and t2.duration_minutes == 65
    sets = session.scalars(
        select(ExerciseSet).where(ExerciseSet.session_id == t.id).order_by(ExerciseSet.set_index)
    ).all()
    assert [(s.set_index, s.reps, s.rir) for s in sets] == [(1, 10, 2), (2, 9, 1)]
    assert len(session.scalars(select(TrainingSession)).all()) == 1


def test_exercises_are_found_by_name_or_alias_and_created_otherwise(session):
    workout_log.save(session, logged(exercises=[{"name": "  bankdrücken ", "sets": [{"reps": 5}]}]))
    workout_log.save(session, logged(exercises=[{"name": "Bankdrücken", "sets": [{"reps": 5}]}]))
    workout_log.save(session, logged(exercises=[{"name": "Klimmzüge", "sets": [{"reps": 8}]}]))
    names = {e.name: e.bodyweight for e in session.scalars(select(Exercise))}
    assert names == {"bankdrücken": True, "Klimmzüge": True}


def test_discard_only_removes_logger_sessions(session):
    data = logged()
    workout_log.save(session, data)
    assert workout_log.discard(session, data.client_id)
    assert not workout_log.discard(session, data.client_id)
    assert session.scalars(select(TrainingSession)).all() == []


def history_of(session, *sessions):
    for i, sets in enumerate(sessions):
        workout_log.save(session, logged(days_ago=len(sessions) - i, exercises=bench(*sets)))
    ex = session.scalar(select(Exercise).where(Exercise.name == "Bankdrücken"))
    return progression.for_exercises(session, [ex])[ex.id]


def test_weight_goes_up_once_every_working_set_hits_the_top_with_rir(session):
    s = history_of(session, [(40, 12, 3), (60, 12, 2), (60, 12, 1), (60, 12, 2)])
    # The 40 kg warm-up is no working set.
    assert (s.action, s.weight_kg, s.reps, s.rir_known) == ("increase", 62.5, 8, True)


def test_too_much_in_reserve_or_missing_reps_keep_the_weight(session):
    s = history_of(session, [(60, 12, 3), (60, 12, 2)])
    assert (s.action, s.weight_kg, s.reps) == ("reps", 60.0, 12)
    s = history_of(session, [(60, 10, 2), (60, 9, 2)])
    assert (s.action, s.weight_kg, s.reps) == ("reps", 60.0, 10)


def test_rep_range_and_step_per_exercise(session):
    workout_log.save(session, logged(exercises=bench((100, 6, 2), (100, 6, 2))))
    ex = session.scalar(select(Exercise))
    ex.rep_min, ex.rep_max, ex.weight_step = 4, 6, 5
    s = progression.for_exercises(session, [ex])[ex.id]
    assert (s.action, s.weight_kg, s.reps) == ("increase", 105.0, 4)


def test_stagnation_after_four_identical_sessions(session):
    same = [(60, 10, 2), (60, 9, 2)]
    s = history_of(session, [(57.5, 10, 2)], same, same, same)
    assert (s.same_sessions, s.stagnant) == (3, False)
    s = history_of(session, same)
    assert (s.same_sessions, s.stagnant) == (4, True)


def test_logger_api(client, session):
    for i, reps in enumerate([10, 12]):
        workout_log.save(
            session, logged("Push A", days_ago=3 - i, exercises=bench((60, reps, 2), (60, reps, 2)))
        )
    session.commit()
    names = client.get("/api/training/log/workouts").json()
    assert [n["name"] for n in names] == ["Push A"]
    template = client.get("/api/training/log/template", params={"workout": "push a"}).json()
    [ex] = template["exercises"]
    assert ex["suggestion"]["weight_kg"] == 62.5 and ex["suggestion"]["reps"] == 8
    assert (
        client.get(f"/api/training/log/exercises/{ex['exercise_id']}").json()["name"]
        == "Bankdrücken"
    )

    body = logged().model_dump(mode="json")
    saved = client.post("/api/training/log", json=body)
    assert saved.status_code == 200 and saved.json()["source"] == "compass"
    assert client.post("/api/training/log", json=body).json()["id"] == saved.json()["id"]
    assert client.post(f"/api/training/log/{body['client_id']}/discard").status_code == 204
    assert client.post(f"/api/training/log/{body['client_id']}/discard").status_code == 404

    progress = client.get("/api/training/progression").json()
    assert progress["suggestions"][0]["action"] == "increase" and progress["stagnant"] == []

    ex_id = ex["exercise_id"]
    assert (
        client.patch(
            f"/api/training/exercises/{ex_id}", json={"rep_min": 12, "rep_max": 6}
        ).status_code
        == 422
    )
    updated = client.patch(
        f"/api/training/exercises/{ex_id}", json={"rep_min": 6, "rep_max": 10, "weight_step": 1.25}
    )
    assert (updated.json()["rep_min"], updated.json()["weight_step"]) == (6, 1.25)


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_progression_mcp_tool(session):
    mcp_db.set_session_factory(lambda: nullcontext(session))
    try:
        same = [(60, 10, None), (60, 10, None)]
        history_of(session, same, same, same, same)
        async with Client(mcp, raise_exceptions=True) as c:
            result = await c.call_tool("progression_suggestions", {})
        data = result.structured_content
        [s] = data["suggestions"]
        assert s["last_sets"] == ["60 kg x 10", "60 kg x 10"]
        assert (s["target_weight_kg"], s["target_reps"], s["rir_known"]) == (60.0, 11, False)
        assert [x["exercise"] for x in data["stagnant"]] == ["Bankdrücken"]
    finally:
        mcp_db.set_session_factory(mcp_db.SessionLocal)
