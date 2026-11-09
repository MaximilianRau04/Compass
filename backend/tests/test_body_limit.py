"""Bodies over the limit get a 413, with or without Content-Length, before any token is checked."""

from app.body_limit import MAX_BODY_BYTES
from app.config import get_settings

MB = b"x" * (1024 * 1024)
CHUNKS = MAX_BODY_BYTES // len(MB) + 1


def chunked():
    """No Content-Length: httpx sends an iterator with Transfer-Encoding: chunked."""
    for _ in range(CHUNKS):
        yield MB


def test_chunked_body_before_the_token_check(client):
    # mail/triage has a JSON body, which FastAPI reads before the token dependency runs.
    response = client.post("/api/ingest/mail/triage", content=chunked())
    assert response.status_code == 413


def test_chunked_body_read_by_the_route(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "healthconnect_token", "secret")
    response = client.post(
        "/api/ingest/healthconnect",
        content=chunked(),
        headers={"Authorization": "Bearer secret", "Content-Type": "application/json"},
    )
    assert response.status_code == 413


def test_content_length_over_the_limit(client):
    response = client.post(
        "/api/ingest/mail/triage",
        content=b"{}",
        headers={"Content-Length": str(MAX_BODY_BYTES + 1)},
    )
    assert response.status_code == 413


def test_small_bodies_pass(client):
    assert client.post("/api/tasks", json={"title": "Task"}).status_code == 201
