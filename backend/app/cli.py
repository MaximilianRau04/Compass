"""Maintenance commands, run inside the api container:

    python -m app.cli rebuild-health

rebuild-health recomputes everything derived from the stored Health Connect records (daily
metrics, meals, weights, Gym Day sessions and their durations). A sync only derives the days it
changes, and unchanged records are skipped, so after a release that derives something new the
existing records need this once.
"""

import argparse
import json
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models.health import HealthRecord
from app.services import health, nutrition

CHUNK_DAYS = 60


def rebuild_health(session: Session) -> dict:
    record_days = set(session.scalars(select(HealthRecord.local_date).distinct()))
    # Records can reach into the next day (sleep, heart rate around midnight).
    days: list[date] = sorted(record_days | {d + timedelta(days=1) for d in record_days})
    for i in range(0, len(days), CHUNK_DAYS):
        chunk = set(days[i : i + CHUNK_DAYS])
        health.recompute_days(session, chunk)
        nutrition.rebuild_from_healthconnect(session, chunk)
    sessions = health.match_gymday_sessions(session, days[0], days[-1]) if days else 0
    watch = health.match_watch_sessions(session, days[0], days[-1]) if days else 0
    return {"days": len(record_days), "gymday_sessions": sessions, "watch_workouts": watch}


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("rebuild-health", help="recompute data derived from Health Connect")
    args = parser.parse_args()

    if args.command == "rebuild-health":
        with SessionLocal() as session:
            result = rebuild_health(session)
            session.commit()
        print(json.dumps(result))


if __name__ == "__main__":
    main()
