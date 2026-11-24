"""Maintenance commands, run inside the api container:

    python -m app.cli rebuild-health
    python -m app.cli revoke-mcp-tokens

rebuild-health recomputes everything derived from the stored Health Connect records (daily
metrics, meals, weights, Gym Day sessions and their durations). A sync only derives the days it
changes, and unchanged records are skipped, so after a release that derives something new the
existing records need this once.

revoke-mcp-tokens logs out every AI assistant (e.g. after a leaked token); each has to connect
again through the login page.
"""

import argparse
import json
import sys
from datetime import date, timedelta
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import crypto
from app.db import SessionLocal
from app.mcp.oauth import revoke_all_tokens
from app.models.credentials import Credential
from app.models.health import HealthRecord
from app.services import embeddings, export, health, integrations, nutrition

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


def rotate_secrets(session: Session) -> dict:
    rotated = 0
    for cred in session.scalars(select(Credential)):
        changed = False
        if cred.secret:
            cred.secret = crypto.rotate(cred.secret)
            changed = True
        if cred.pending:
            cred.pending = crypto.rotate(cred.pending)
            changed = True
        if changed:
            rotated += 1
    session.flush()
    return {"rotated": rotated}


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("rebuild-health", help="recompute data derived from Health Connect")
    commands.add_parser("revoke-mcp-tokens", help="log out every MCP client")
    commands.add_parser(
        "rotate-secrets", help="re-encrypt stored credentials with the current COMPASS_SECRET_KEY"
    )
    verify = commands.add_parser("verify-export", help="validate a Compass export zip file")
    verify.add_argument("path", type=Path, help="path to compass-export-*.zip")
    report = commands.add_parser(
        "report-status", help="record an external job status (e.g. ops:backup) in integration_state"
    )
    report.add_argument("name", help="integration name, e.g. ops:backup or ops:deploy")
    report.add_argument("--error", default=None, help="failure reason; omit to record success")
    commands.add_parser(
        "backfill-embeddings", help="compute pgvector embeddings for notes and journal entries"
    )
    args = parser.parse_args()

    if args.command == "rebuild-health":
        with SessionLocal() as session:
            result = rebuild_health(session)
            session.commit()
        print(json.dumps(result))
    elif args.command == "revoke-mcp-tokens":
        print(json.dumps({"revoked": revoke_all_tokens()}))
    elif args.command == "rotate-secrets":
        with SessionLocal() as session:
            result = rotate_secrets(session)
            session.commit()
        print(json.dumps(result))
    elif args.command == "verify-export":
        try:
            counts = export.verify_zip(args.path.read_bytes())
        except (OSError, ValueError) as exc:
            print(f"export invalid: {exc}", file=sys.stderr)
            raise SystemExit(1) from None
        print(json.dumps({"ok": True, "tables": len(counts), "rows": sum(counts.values())}))
    elif args.command == "report-status":
        with SessionLocal() as session:
            if args.error:
                integrations.record_failure(session, args.name, args.error)
            else:
                integrations.record_success(session, args.name, {})
            session.commit()
        print(json.dumps({"name": args.name, "ok": not args.error}))
    elif args.command == "backfill-embeddings":
        with SessionLocal() as session:
            result = embeddings.backfill(session)
            session.commit()
        print(json.dumps(result))


if __name__ == "__main__":
    main()
