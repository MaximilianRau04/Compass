import errno
import socket
import urllib.error
from datetime import UTC, date, datetime, timedelta

from app.models.integrations import IntegrationState
from app.services import briefs, integrations, notify


def test_describe_error_formats_network_and_http_errors():
    assert (
        integrations.describe_error(
            urllib.error.HTTPError("https://x", 502, "Bad Gateway", None, None)
        )
        == "HTTP 502 Bad Gateway"
    )
    assert (
        integrations.describe_error(urllib.error.URLError(socket.gaierror("nope")))
        == "host name not found (DNS)"
    )
    assert (
        integrations.describe_error(TimeoutError()) == "server not reachable (timeout or no route)"
    )
    assert (
        integrations.describe_error(OSError(errno.ENETUNREACH, "Network is unreachable"))
        == "server not reachable (timeout or no route)"
    )


def test_integration_state_lifecycle_and_ops_sync_alert(session):
    integrations.record_success(session, "ops:backup", {"files": 1})
    integrations.record_failure(session, "ops:deploy", "health check timed out")
    session.flush()

    ops = integrations.list_states(session, "ops:")
    assert [s.name for s in ops] == ["ops:backup", "ops:deploy"]
    assert ops[0].last_error is None
    assert ops[1].last_error == "health check timed out"

    # Backdate the failure so it crosses the sync alert window.
    deploy = session.get(IntegrationState, "ops:deploy")
    now = datetime.now(UTC)
    deploy.created_at = now - timedelta(hours=10)
    session.flush()

    failures = notify._sync_failures(session, now, timedelta(hours=6))
    assert any(
        source == "ops:deploy" and err == "health check timed out" for _, source, err in failures
    )

    integrations.clear(session, "ops:deploy")
    session.flush()
    assert session.get(IntegrationState, "ops:deploy") is None


def test_briefs_upsert_replaces_same_kind_and_day(session):
    day = date(2026, 11, 15)
    first = briefs.save(session, "daily", "First body", title="Morning", day=day)
    second = briefs.save(session, "daily", "Second body", title="Updated", day=day)
    session.flush()
    assert first.id == second.id
    assert briefs.latest(session, "daily", since=day).body == "Second body"
    assert len(briefs.recent(session, kind="daily", limit=5)) == 1
