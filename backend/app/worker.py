"""Scheduler entrypoint: runs ingestion and cron jobs."""

import logging

from apscheduler.schedulers.blocking import BlockingScheduler
from sqlalchemy import text

from app.config import get_settings
from app.db import engine

log = logging.getLogger("compass.worker")


def heartbeat() -> None:
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    log.info("heartbeat ok")


def main() -> None:
    settings = get_settings()
    logging.basicConfig(level=settings.log_level)
    scheduler = BlockingScheduler(timezone=settings.timezone)
    scheduler.add_job(heartbeat, "interval", minutes=5, id="heartbeat")
    log.info("worker started")
    heartbeat()
    scheduler.start()


if __name__ == "__main__":
    main()
