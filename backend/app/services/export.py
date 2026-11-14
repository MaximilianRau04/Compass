"""Everything Compass stores, as one zip with a JSON file per table, to keep a copy or move to
another tool. Secrets stay out: sign-in tokens, the OAuth tables, push keys, the session ids of
bank consents and feed links (only their host). Only what is on the lists below is left out, so
tests/test_export.py lists every exported table and column: a new one has to be looked at. Raw
health records are left out too, they are large and only the phone's data again; the tables
derived from them are in."""

import io
import json
import zipfile
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from urllib.parse import urlsplit

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
# Columns that would let somebody act in the user's name. A feed link can carry a secret token
# (a calendar subscription), so only its host is exported, like the API sends it.
SKIP_COLUMNS = {
    "bank_connections": {"session_id", "state"},
    "feeds": {"url"},
    # The search index of the notes, built from title and body.
    "notes": {"search"},
}
HOST_OF = {"feeds": "url"}


def _plain(value: Any) -> Any:
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return value


def columns() -> dict[str, list[str]]:
    """The exported tables with the keys of their rows."""
    out = {}
    for table in Base.metadata.sorted_tables:
        if table.name in SKIP_TABLES:
            continue
        skip = SKIP_COLUMNS.get(table.name, set())
        names = [c.name for c in table.columns if c.name not in skip]
        out[table.name] = names + (["host"] if table.name in HOST_OF else [])
    return out


def export_zip(session: Session) -> bytes:
    buffer = io.BytesIO()
    counts = {}
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for table in Base.metadata.sorted_tables:
            if table.name in SKIP_TABLES:
                continue
            skip = SKIP_COLUMNS.get(table.name, set())
            columns = [c for c in table.columns if c.name not in skip]
            secret = table.columns[HOST_OF[table.name]] if table.name in HOST_OF else None
            selected = [*columns, secret] if secret is not None else columns
            rows = []
            for row in session.execute(select(*selected).order_by(*table.primary_key.columns)):
                item = {c.name: _plain(v) for c, v in zip(columns, row, strict=False)}
                if secret is not None:
                    item["host"] = urlsplit(row[-1]).hostname if row[-1] else None
                rows.append(item)
            counts[table.name] = len(rows)
            archive.writestr(
                f"{table.name}.json", json.dumps(rows, ensure_ascii=False, indent=1, default=str)
            )
        archive.writestr(
            "manifest.json",
            json.dumps({"exported_at": utc_now().isoformat(), "tables": counts}, indent=1),
        )
    return buffer.getvalue()
