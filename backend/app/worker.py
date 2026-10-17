"""Scheduler entrypoint: runs ingestion and cron jobs."""

import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from apscheduler.schedulers.blocking import BlockingScheduler
from sqlalchemy import text

from app.config import get_settings
from app.db import SessionLocal, engine
from app.ingestion import calendar

log = logging.getLogger("compass.worker")


def heartbeat() -> None:
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    log.info("heartbeat ok")


def sync_calendars() -> None:
    if not get_settings().calendar_feeds:
        log.debug("no calendar feeds configured")
        return
    calendar.sync_all(SessionLocal)


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
    )
    log.info("worker started, calendar feeds: %s", ", ".join(settings.calendar_feeds) or "none")
    heartbeat()
    scheduler.start()


if __name__ == "__main__":
    main()
