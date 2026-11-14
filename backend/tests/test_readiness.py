from datetime import timedelta

from app.models.health import DailyMetrics
from app.services import readiness
from app.services.clock import local_today
from tests.test_analysis import sleep
from tests.test_healthconnect import at, ingest

TODAY = local_today()


def resting(session, today_bpm, usual=55, days=14):
    # A synced night already made rows for its days; set the resting heart rate on those.
    for i in range(days + 1):
        day = TODAY - timedelta(days=i)
        row = session.get(DailyMetrics, day)
        if row is None:
            row = DailyMetrics(local_date=day, updated_at=at(TODAY, "08:00"))
            session.add(row)
        row.resting_hr = today_bpm if i == 0 else usual
    session.flush()


def test_no_score_without_last_night(session):
    resting(session, 55)
    r = readiness.readiness(session, TODAY)
    assert r.score is None and r.level is None and r.reasons == []


def test_a_good_night_and_usual_resting_hr_is_good(session):
    ingest(session, [sleep("n", TODAY, 1, "23:00", "07:00")])
    resting(session, 55)
    r = readiness.readiness(session, TODAY)
    assert (r.score, r.level, r.reasons) == (100, "good", [])


def test_a_short_night_and_a_raised_resting_hr_take_points_off(session):
    ingest(session, [sleep("n", TODAY, 0, "02:00", "07:00")])
    resting(session, 61)
    r = readiness.readiness(session, TODAY)
    assert r.reasons == ["short_sleep", "resting_up"]
    assert (r.score, r.level) == (45, "low")
