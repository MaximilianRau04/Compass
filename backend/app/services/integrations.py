"""Bookkeeping for data sources: when they last ran, whether it worked and what changed."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.integrations import IntegrationState
from app.services.clock import utc_now


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


def list_states(session: Session) -> list[IntegrationState]:
    return list(session.scalars(select(IntegrationState).order_by(IntegrationState.name)))
