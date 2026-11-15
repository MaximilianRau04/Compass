from datetime import date

from app.models.news import Brief
from app.services import journal, monthly
from tests.test_analysis import sleep
from tests.test_healthconnect import ingest


def test_month_bounds():
    assert monthly.month_bounds(date(2026, 2, 14)) == (date(2026, 2, 1), date(2026, 2, 28))
    assert monthly.month_bounds(date(2026, 12, 31)) == (date(2026, 12, 1), date(2026, 12, 31))


def test_review_of_the_last_full_month_against_the_one_before(session, monkeypatch):
    monkeypatch.setattr(journal, "local_today", lambda: date(2026, 11, 1))
    ingest(session, [sleep("a", date(2026, 10, 10), 1, "23:00", "07:00")])
    ingest(session, [sleep("b", date(2026, 9, 10), 1, "23:00", "06:00")])
    journal.save(session, date(2026, 10, 12), mood=4, energy=2)
    r = monthly.monthly_review(session, date(2026, 11, 1))
    assert (r.month, r.since, r.until) == ("2026-10", date(2026, 10, 1), date(2026, 10, 31))
    assert r.now.days == 31 and r.before.days == 30
    assert (r.now.sleep_avg_minutes, r.before.sleep_avg_minutes) == (480, 420)
    assert (r.now.mood, r.now.energy, r.now.journal_days) == (4, 2, 1)
    text = monthly.markdown(r)
    assert "8:00 h (month before 7:00 h)" in text
    assert "Mood 4.0" in text or "Mood 4" in text


def test_save_monthly_stores_a_brief(session):
    monthly.save_monthly(session, date(2026, 11, 1))
    brief = session.query(Brief).filter(Brief.kind == "monthly").one()
    assert brief.local_date == date(2026, 11, 1) and brief.title == "Monthly review 2026-10"
