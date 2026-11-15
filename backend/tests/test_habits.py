from datetime import timedelta

import pytest

from app.services import habits, journal, nutrition
from app.services.clock import local_today

TODAY = local_today()


def test_a_manual_habit_counts_its_streak(session):
    h = habits.create(session, "  Lesen ")
    assert h.name == "Lesen"
    for i in (1, 2, 3, 5):
        habits.check(session, h, TODAY - timedelta(days=i), True)
    [s] = habits.statuses(session, TODAY)
    # Today is still open: the streak runs up to yesterday.
    assert (s.done_today, s.streak) == (False, 3)
    habits.check(session, h, TODAY, True)
    assert habits.statuses(session, TODAY)[0].streak == 4
    habits.check(session, h, TODAY - timedelta(days=2), False)
    assert habits.statuses(session, TODAY)[0].streak == 2


def test_rules_follow_the_data(session):
    nutrition.set_goal(session, "steps", 8000, TODAY - timedelta(days=30))
    steps = habits.create(session, "Schritte", "steps_goal")
    diary = habits.create(session, "Tagebuch", "journal")
    journal.save(session, TODAY, mood=4)
    by_name = {s.habit.name: s for s in habits.statuses(session, TODAY)}
    assert by_name["Tagebuch"].done_today and by_name["Tagebuch"].streak == 1
    assert not by_name["Schritte"].done_today
    with pytest.raises(habits.HabitError):
        habits.check(session, steps, TODAY, True)
    assert diary.rule == "journal"


def test_unknown_rules_and_future_days_are_refused(session):
    with pytest.raises(habits.HabitError):
        habits.create(session, "x", "luck")
    h = habits.create(session, "x")
    with pytest.raises(habits.HabitError):
        habits.check(session, h, TODAY + timedelta(days=1), True)


def test_habits_api(client, session):
    created = client.post("/api/habits", json={"name": "Dehnen"})
    assert created.status_code == 201
    hid = created.json()["id"]
    assert client.post("/api/habits", json={"name": "x", "rule": "nope"}).status_code == 422
    day = TODAY.isoformat()
    assert (
        client.put(f"/api/habits/{hid}/check", json={"day": day, "done": True}).status_code == 204
    )
    [h] = client.get("/api/habits").json()
    assert h["done_today"] and h["streak"] == 1 and len(h["days"]) == habits.WINDOW
    assert client.delete(f"/api/habits/{hid}").status_code == 204
    assert client.get("/api/habits").json() == []
    assert client.delete(f"/api/habits/{hid}").status_code == 404
