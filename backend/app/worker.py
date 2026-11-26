"""Scheduler entrypoint: runs ingestion and cron jobs."""

import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from apscheduler.schedulers.blocking import BlockingScheduler
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app import i18n
from app.config import get_settings
from app.db import SessionLocal, engine
from app.ingestion import calendar
from app.ingestion import mail as mail_sync
from app.ingestion import news as news_sync
from app.services import feeds

log = logging.getLogger("compass.worker")

# APScheduler drops a run that starts more than 1 s late by default. The first run is due "now",
# but the worker connects to the database before the scheduler starts, so it was always dropped
# and the first sync only came one interval later.
MISFIRE_GRACE_SECONDS = 300


def heartbeat() -> None:
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    log.info("heartbeat ok")


def sync_calendars() -> None:
    calendar.sync_all(SessionLocal)


def sync_mail() -> None:
    try:
        accounts = get_settings().mail_accounts
    except ValueError as exc:
        log.warning("mail: %s", exc)
        return
    if not accounts:
        log.debug("no mail accounts configured")
        return
    for account, result in mail_sync.sync_all(SessionLocal).items():
        log.info("mail %s: %s", account, result)


def sync_news() -> None:
    results = news_sync.sync_all(SessionLocal)
    failed = [feed for feed, result in results.items() if isinstance(result, str)]
    log.info("news: %d feeds, failed: %s", len(results), ", ".join(failed) or "none")


def weekly_review() -> None:
    from app.services import notify, review

    with SessionLocal() as session:
        r = review.save_weekly(session)
        session.commit()
        notify.weekly_review(session, i18n.t("review.ready"), review.headline(r), r.until)
        session.commit()
    log.info("weekly review saved")


def monthly_review() -> None:
    from app.services import monthly

    with SessionLocal() as session:
        r = monthly.save_monthly(session)
        session.commit()
    log.info("monthly review %s saved", r.month)


def sync_finance() -> None:
    from app.services import enablebanking, finance

    if not enablebanking.configured():
        log.debug("enable banking not configured")
        return
    with SessionLocal() as session:
        result = finance.sync(session)
        session.commit()
    if result:
        log.info("finance: %s", result)


def depot_prices() -> None:
    from app.services import finance

    with SessionLocal() as session:
        try:
            value = finance.refresh_depot(session)
        except finance.FinanceError as exc:
            log.warning("depot: %s", exc)
            return
        session.commit()
    if value is not None:
        log.info("depot: %.2f", value)


def notifications() -> None:
    from app.services import notify, push

    if not push.enabled():
        return
    with SessionLocal() as session:
        sent = notify.check_all(session, datetime.now(ZoneInfo(get_settings().timezone)))
    if any(sent.values()):
        log.info("push: %s", sent)


def feed_names() -> str:
    try:
        with SessionLocal() as session:
            return ", ".join(feeds.calendars(session)) or "none"
    except ValueError as exc:
        return f"invalid configuration ({exc})"
    except SQLAlchemyError:  # the API runs the migrations and may not be done yet
        return "unknown until the database is ready"


def main() -> None:
    settings = get_settings()
    logging.basicConfig(level=settings.log_level)
    scheduler = BlockingScheduler(timezone=settings.timezone)
    scheduler.add_job(heartbeat, "interval", minutes=5, id="heartbeat")
    scheduler.add_job(
        sync_calendars,
        "interval",
        minutes=settings.calendar_sync_minutes,
        id="calendars",
        # Aware, so the first run is now and not misread in the scheduler's time zone.
        next_run_time=datetime.now(ZoneInfo(settings.timezone)),
        max_instances=1,
        coalesce=True,
        misfire_grace_time=MISFIRE_GRACE_SECONDS,
    )
    scheduler.add_job(
        sync_mail,
        "interval",
        minutes=settings.mail_sync_minutes,
        id="mail",
        next_run_time=datetime.now(ZoneInfo(settings.timezone)),
        max_instances=1,
        coalesce=True,
        misfire_grace_time=MISFIRE_GRACE_SECONDS,
    )
    scheduler.add_job(
        sync_news,
        "interval",
        minutes=settings.news_sync_minutes,
        id="news",
        next_run_time=datetime.now(ZoneInfo(settings.timezone)),
        max_instances=1,
        coalesce=True,
        misfire_grace_time=MISFIRE_GRACE_SECONDS,
    )
    # Sunday evening: the week is over, the review lands on the dashboard as a brief.
    scheduler.add_job(
        weekly_review,
        "cron",
        day_of_week="sun",
        hour=20,
        id="weekly-review",
        max_instances=1,
        coalesce=True,
        misfire_grace_time=6 * 3600,
    )
    # The 1st in the morning: last month is over, the review lands on the dashboard as a brief.
    scheduler.add_job(
        monthly_review,
        "cron",
        day=1,
        hour=7,
        id="monthly-review",
        max_instances=1,
        coalesce=True,
        misfire_grace_time=12 * 3600,
    )
    scheduler.add_job(
        sync_finance,
        "interval",
        hours=settings.finance_sync_hours,
        id="finance",
        next_run_time=datetime.now(ZoneInfo(settings.timezone)),
        max_instances=1,
        coalesce=True,
        misfire_grace_time=MISFIRE_GRACE_SECONDS,
    )
    # After the close in Frankfurt (17:30) and New York (22:00).
    scheduler.add_job(
        depot_prices,
        "cron",
        hour=22,
        minute=30,
        id="depot",
        max_instances=1,
        coalesce=True,
        misfire_grace_time=6 * 3600,
    )
    scheduler.add_job(
        notifications,
        "interval",
        minutes=5,
        id="notifications",
        max_instances=1,
        coalesce=True,
        misfire_grace_time=MISFIRE_GRACE_SECONDS,
    )
    log.info("worker started, calendar feeds: %s", feed_names())
    heartbeat()
    scheduler.start()


if __name__ == "__main__":
    main()
