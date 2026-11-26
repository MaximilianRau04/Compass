"""The worker's wiring: every job is scheduled, and the jobs run against the database.

The syncs themselves are tested in their own modules; here they are replaced by stubs, so no test
reaches a calendar, mailbox or feed from the developer's .env.
"""

from contextlib import nullcontext

from apscheduler.schedulers.blocking import BlockingScheduler

from app import worker
from app.models.news import Brief
from app.services import enablebanking, push


def test_main_schedules_every_job(monkeypatch):
    started = []
    monkeypatch.setattr(BlockingScheduler, "start", lambda self: started.append(self))
    monkeypatch.setattr(worker, "heartbeat", lambda: None)
    monkeypatch.setattr(worker, "feed_names", lambda: "none")

    worker.main()

    jobs = {job.id: job for job in started[0].get_jobs()}
    assert set(jobs) == {
        "heartbeat",
        "calendars",
        "mail",
        "news",
        "weekly-review",
        "monthly-review",
        "finance",
        "depot",
        "notifications",
    }
    review = str(jobs["weekly-review"].trigger)
    assert "day_of_week='sun'" in review and "hour='20'" in review
    monthly = str(jobs["monthly-review"].trigger)
    assert "day='1'" in monthly and "hour='7'" in monthly


def test_jobs_run_against_the_database(monkeypatch, session, engine):
    monkeypatch.setattr(worker, "SessionLocal", lambda: nullcontext(session))
    monkeypatch.setattr(worker, "engine", engine)
    factories = []

    def sync_all(factory):
        factories.append(factory)
        return {}

    monkeypatch.setattr(worker.calendar, "sync_all", sync_all)
    monkeypatch.setattr(worker.news_sync, "sync_all", sync_all)
    monkeypatch.setattr(enablebanking, "configured", lambda: False)
    monkeypatch.setattr(push, "enabled", lambda: True)

    worker.heartbeat()
    worker.sync_calendars()
    worker.sync_news()
    worker.sync_finance()
    worker.depot_prices()  # no positions: no price is fetched
    worker.notifications()  # no device subscribed: nothing is sent
    worker.weekly_review()
    worker.monthly_review()

    assert factories == [worker.SessionLocal, worker.SessionLocal]
    assert session.query(Brief).filter(Brief.kind == "weekly").count() == 1
    assert session.query(Brief).filter(Brief.kind == "monthly").count() == 1
