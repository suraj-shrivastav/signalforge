"""Integration fixtures. They need a migrated Postgres and never run implicitly.

Set TEST_DATABASE_URL to a database already at ``alembic upgrade head``. CI does
this against a throwaway service container. Each test runs inside a transaction
that is rolled back, so tests leave no rows behind.
"""

import os
from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from signalforge.db.session import normalise_dsn


@pytest.fixture
def db_session() -> Iterator[Session]:
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL not set")
    engine = create_engine(normalise_dsn(url))
    connection = engine.connect()
    outer = connection.begin()
    # create_savepoint: session.commit() inside the code under test releases a
    # savepoint, and the outer transaction is still rolled back at the end.
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    try:
        yield session
    finally:
        session.close()
        outer.rollback()
        connection.close()
        engine.dispose()
