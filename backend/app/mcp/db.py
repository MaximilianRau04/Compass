"""Database sessions for the MCP server.

Tools and the OAuth provider open a short session per call. Tests swap the factory to run
everything inside their rolled-back test transaction.
"""

from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager

from sqlalchemy.orm import Session

from app.db import SessionLocal

SessionFactory = Callable[[], AbstractContextManager[Session]]
_factory: SessionFactory = SessionLocal


def set_session_factory(factory: SessionFactory) -> None:
    global _factory
    _factory = factory


@contextmanager
def session_scope() -> Iterator[Session]:
    with _factory() as session:
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
