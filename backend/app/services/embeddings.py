"""Optional semantic search embeddings (pgvector) for notes and journal entries.

Supports both OpenAI-compatible `/v1/embeddings` and Ollama `/api/embed` or `/api/embeddings`.
When EMBEDDING_URL or EMBEDDING_MODEL is empty, all calls are silent no-ops and search falls back
to Postgres full-text search alone. Network errors are logged and never fail a note or journal save.
"""

import json
import logging
import urllib.request

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.journal import JournalEntry
from app.models.notes import Note

log = logging.getLogger("compass.embeddings")

MAX_INPUT_CHARS = 8_000
TIMEOUT_SECONDS = 10
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


def embed(text: str) -> list[float] | None:
    """Return an embedding vector for `text`, or None if disabled or unreachable."""
    if not configured():
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
        with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        return parse_response(payload)
    except Exception as exc:
        log.warning("embedding request failed: %s", exc)
        return None


def embed_note(note: Note) -> None:
    if not configured():
        return
    text = f"{note.title}\n\n{note.body}".strip()
    vec = embed(text)
    if vec is not None:
        note.embedding = vec


def embed_journal(entry: JournalEntry) -> None:
    if not configured():
        return
    if not entry.text.strip():
        entry.embedding = None
        return
    vec = embed(entry.text)
    if vec is not None:
        entry.embedding = vec


def backfill(session: Session) -> dict[str, int]:
    """Compute embeddings for all notes and journal entries that do not have one yet."""
    if not configured():
        return {"notes": 0, "journal": 0}
    notes_done = 0
    for note in session.scalars(select(Note).where(Note.embedding.is_(None))):
        embed_note(note)
        if note.embedding is not None:
            notes_done += 1
    journal_done = 0
    for entry in session.scalars(select(JournalEntry).where(JournalEntry.embedding.is_(None))):
        if not entry.text.strip():
            continue
        embed_journal(entry)
        if entry.embedding is not None:
            journal_done += 1
    session.flush()
    return {"notes": notes_done, "journal": journal_done}
