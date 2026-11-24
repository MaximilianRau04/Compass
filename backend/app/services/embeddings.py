"""Optional semantic search embeddings (pgvector) for notes and journal entries.

Supports both OpenAI-compatible `/v1/embeddings` and Ollama `/api/embed` or `/api/embeddings`.
When EMBEDDING_URL or EMBEDDING_MODEL is empty, all calls are silent no-ops and search falls back
to Postgres full-text search alone. Network errors are logged and never fail a note or journal save.
"""

import json
import logging
import time
import urllib.request

from sqlalchemy import Float, Select, case, cast, func, literal, or_, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.journal import JournalEntry
from app.models.notes import Note
from app.models.vector import Vector

log = logging.getLogger("compass.embeddings")

MAX_INPUT_CHARS = 8_000
TIMEOUT_SECONDS = 10
# A search waits less, and after a failure the server is left alone for a while, so a down
# embedding server doesn't slow every search (and every keystroke in the search field).
QUERY_TIMEOUT_SECONDS = 3
PAUSE_AFTER_FAILURE_SECONDS = 60
_down_until = 0.0
# Cosine distance threshold (0 = identical, 1 = orthogonal, 2 = opposite).
MAX_COSINE_DISTANCE = 0.55


def configured() -> bool:
    s = get_settings()
    return bool(s.embedding_url.strip() and s.embedding_model.strip())


def parse_response(payload: dict) -> list[float] | None:
    """Extract the embedding vector from OpenAI or Ollama JSON responses."""
    if isinstance(payload.get("data"), list) and payload["data"]:
        first = payload["data"][0]
        if isinstance(first, dict) and isinstance(first.get("embedding"), list):
            return [float(x) for x in first["embedding"]]
    if isinstance(payload.get("embeddings"), list) and payload["embeddings"]:
        first = payload["embeddings"][0]
        if isinstance(first, list):
            return [float(x) for x in first]
    if isinstance(payload.get("embedding"), list):
        return [float(x) for x in payload["embedding"]]
    return None


def embed(text: str, timeout: float = TIMEOUT_SECONDS) -> list[float] | None:
    """Return an embedding vector for `text`, or None if disabled or unreachable."""
    global _down_until
    if not configured() or time.monotonic() < _down_until:
        return None
    clean = " ".join(text.split())[:MAX_INPUT_CHARS]
    if not clean:
        return None
    s = get_settings()
    url = s.embedding_url.strip()
    # Ollama legacy /api/embeddings uses "prompt", newer /api/embed and OpenAI use "input".
    key = "prompt" if url.rstrip("/").endswith("/api/embeddings") else "input"
    body = json.dumps({"model": s.embedding_model.strip(), key: clean}).encode()
    headers = {"Content-Type": "application/json", "User-Agent": "Compass embeddings"}
    if s.embedding_api_key.strip():
        headers["Authorization"] = f"Bearer {s.embedding_api_key.strip()}"
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        return parse_response(payload)
    except Exception as exc:
        log.warning("embedding request failed: %s", exc)
        _down_until = time.monotonic() + PAUSE_AFTER_FAILURE_SECONDS
        return None


def embed_query(text: str) -> list[float] | None:
    return embed(text, timeout=QUERY_TIMEOUT_SECONDS)


def nearest(stmt: Select, column, vec: list[float]) -> Select:
    """Narrow `stmt` to rows whose embedding is close to `vec`, the closest first."""
    # Vectors of an earlier model with other dims would make <=> raise. Postgres may evaluate
    # WHERE conditions in any order, only CASE guarantees <=> never sees them.
    distance = case(
        (
            func.vector_dims(column) == len(vec),
            column.op("<=>", return_type=Float)(cast(literal(vec, type_=Vector), Vector)),
        ),
    )
    return stmt.where(column.is_not(None), distance <= MAX_COSINE_DISTANCE).order_by(distance)


def embed_note(note: Note) -> None:
    if not configured():
        return
    # None on failure, so the backfill picks it up later instead of keeping an outdated vector.
    note.embedding = embed(f"{note.title}\n\n{note.body}".strip())


def embed_journal(entry: JournalEntry) -> None:
    if not configured():
        return
    entry.embedding = embed(entry.text) if entry.text.strip() else None


def backfill(session: Session, everything: bool = False) -> dict[str, int]:
    """Compute embeddings for notes and journal entries without one, or with one of another
    size (the model changed). `everything` redoes all, for a new model of the same size."""
    if not configured():
        return {"notes": 0, "journal": 0}
    probe = embed("probe")
    if probe is None:
        raise RuntimeError("the embedding server gave no vector, check EMBEDDING_URL and _MODEL")

    def todo(model, column):
        stmt = select(model)
        if not everything:
            stmt = stmt.where(or_(column.is_(None), func.vector_dims(column) != len(probe)))
        return session.scalars(stmt)

    notes_done = 0
    for note in todo(Note, Note.embedding):
        embed_note(note)
        notes_done += note.embedding is not None
    journal_done = 0
    for entry in todo(JournalEntry, JournalEntry.embedding):
        embed_journal(entry)
        journal_done += entry.embedding is not None
    session.flush()
    return {"notes": notes_done, "journal": journal_done}
