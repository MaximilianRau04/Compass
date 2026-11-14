"""Everything Compass stores, as one zip with a JSON file per table, to keep a copy or move to
another tool. Secrets stay out: sign-in tokens, the OAuth tables, push keys, and the session ids of
bank consents. Raw health records are left out too, they are large and only the phone's data
again; the tables derived from them are in."""

import io
import json
import zipfile
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Base
from app.services.clock import utc_now

SKIP_TABLES = {
    "credentials",
    "oauth_clients",
    "oauth_requests",
    "oauth_codes",
    "oauth_tokens",
    "push_subscriptions",
    "push_sent",
    "health_records",
    "heart_rate",
}
# Columns that would let somebody act in the user's name.
SKIP_COLUMNS = {"bank_connections": {"session_id", "state"}}


def _plain(value: Any) -> Any:
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return value


def tables() -> list[str]:
    return [t.name for t in Base.metadata.sorted_tables if t.name not in SKIP_TABLES]


def export_zip(session: Session) -> bytes:
    buffer = io.BytesIO()
    counts = {}
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for table in Base.metadata.sorted_tables:
            if table.name in SKIP_TABLES:
                continue
            skip = SKIP_COLUMNS.get(table.name, set())
            columns = [c for c in table.columns if c.name not in skip]
            rows = [
                {c.name: _plain(v) for c, v in zip(columns, row, strict=True)}
                for row in session.execute(select(*columns).order_by(*table.primary_key.columns))
            ]
            counts[table.name] = len(rows)
            archive.writestr(
                f"{table.name}.json", json.dumps(rows, ensure_ascii=False, indent=1, default=str)
            )
        archive.writestr(
            "manifest.json",
            json.dumps({"exported_at": utc_now().isoformat(), "tables": counts}, indent=1),
        )
    return buffer.getvalue()
