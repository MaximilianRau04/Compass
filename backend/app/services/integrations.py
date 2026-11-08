"""Bookkeeping for data sources: when they last ran, whether it worked and what changed."""

import errno
import socket
import urllib.error

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.integrations import IntegrationState
from app.services.clock import utc_now

UNREACHABLE = {errno.ENETUNREACH, errno.EHOSTUNREACH, errno.ECONNREFUSED, errno.ETIMEDOUT}


def describe_error(exc: Exception) -> str:
    """A short, readable reason for a failed fetch. Python reports only the last address it
    tried: ILIAS times out over IPv4 and then fails over IPv6, which the server does not have,
    so a down server read as "Network is unreachable"."""
    if isinstance(exc, urllib.error.HTTPError):
        return f"HTTP {exc.code} {exc.reason}".strip()
    reason = exc.reason if isinstance(exc, urllib.error.URLError) else exc
    if isinstance(reason, socket.gaierror):
        return "host name not found (DNS)"
    if isinstance(reason, TimeoutError | socket.timeout) or (
        isinstance(reason, OSError) and reason.errno in UNREACHABLE
    ):
        return "server not reachable (timeout or no route)"
    return f"{type(exc).__name__}: {exc}"


def _state(session: Session, name: str) -> IntegrationState:
    state = session.get(IntegrationState, name)
    if state is None:
        state = IntegrationState(name=name, stats={})
        session.add(state)
    return state


def record_success(session: Session, name: str, stats: dict) -> None:
    state = _state(session, name)
    now = utc_now()
    state.last_run_at = now
    state.last_success_at = now
    state.last_error = None
    state.stats = stats


def record_failure(session: Session, name: str, error: str) -> None:
    state = _state(session, name)
    state.last_run_at = utc_now()
    state.last_error = error[:2000]


def clear(session: Session, name: str) -> None:
    state = session.get(IntegrationState, name)
    if state is not None:
        session.delete(state)


def list_states(session: Session, prefix: str = "") -> list[IntegrationState]:
    """All states, or those whose name starts with prefix (e.g. "news:"), by name."""
    stmt = select(IntegrationState).order_by(IntegrationState.name)
    if prefix:
        stmt = stmt.where(IntegrationState.name.startswith(prefix, autoescape=True))
    return list(session.scalars(stmt))
