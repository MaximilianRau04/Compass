import os

# Fixed values so the tests do not depend on the developer's .env (env vars beat .env).
os.environ["MCP_PUBLIC_URL"] = "http://localhost:8001"

from collections.abc import Iterator

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_session
from app.main import app


@pytest.fixture(scope="session")
def engine() -> Iterator[Engine]:
    """Fresh <db>_test database, migrated with Alembic (so seed data exists too)."""
    url = make_url(get_settings().database_url)
    test_url = url.set(database=f"{url.database}_test")
    admin = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS "{test_url.database}" WITH (FORCE)'))
        conn.execute(text(f'CREATE DATABASE "{test_url.database}"'))
    admin.dispose()

    config = Config("alembic.ini")
    config.attributes["url"] = test_url.render_as_string(hide_password=False)
    command.upgrade(config, "head")

    engine = create_engine(test_url)
    yield engine
    engine.dispose()


@pytest.fixture
def session(engine: Engine) -> Iterator[Session]:
    """Session inside a transaction that is rolled back after the test."""
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(
        bind=connection, join_transaction_mode="create_savepoint", expire_on_commit=False
    )
    yield session
    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture
def client(session: Session) -> Iterator[TestClient]:
    app.dependency_overrides[get_session] = lambda: session
    yield TestClient(app)
    app.dependency_overrides.clear()
