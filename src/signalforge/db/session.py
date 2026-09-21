"""Engine and session construction.

One database, two connections (ADR-0003): session mode for the worker and
Alembic, which need ``LISTEN/NOTIFY`` and a stable session, and transaction mode
for the API's short transactions. Each needs different engine settings, so
callers name the mode instead of relying on a default that is wrong for one.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from enum import StrEnum
from typing import Any

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from signalforge.core.config import Settings
from signalforge.core.errors import ConfigurationError

PSYCOPG_DRIVER = "postgresql+psycopg"


class ConnectionMode(StrEnum):
    SESSION = "session"
    TRANSACTION = "transaction"


def normalise_dsn(dsn: str) -> str:
    """Pin the psycopg3 driver.

    A bare ``postgresql://`` URL makes SQLAlchemy load psycopg2, which is not a
    dependency, so the failure would surface as a confusing import error.
    """
    scheme, separator, rest = dsn.partition("://")
    if not separator:
        raise ConfigurationError("Database URL is missing a scheme", context={"scheme": scheme})
    if "+" in scheme:
        return dsn
    return f"{PSYCOPG_DRIVER}://{rest}"


def engine_options(settings: Settings, mode: ConnectionMode) -> dict[str, Any]:
    """Engine keyword arguments for a connection mode. Separated out to be testable."""
    options: dict[str, Any] = {"pool_pre_ping": True, "future": True}
    if mode is ConnectionMode.SESSION:
        options["url"] = normalise_dsn(settings.worker_database_url)
        options["pool_size"] = 5
        options["max_overflow"] = 5
    else:
        options["url"] = normalise_dsn(settings.api_database_url)
        options["pool_size"] = 10
        options["max_overflow"] = 0
        # Supavisor and pgbouncer cannot keep prepared statements across pooled
        # transactions; caching them produces "prepared statement already
        # exists" errors under load.
        options["connect_args"] = {"prepare_threshold": None}
    return options


def create_db_engine(settings: Settings, mode: ConnectionMode) -> Engine:
    options = engine_options(settings, mode)
    url = options.pop("url")
    return create_engine(url, **options)


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)


@contextmanager
def session_scope(factory: sessionmaker[Session]) -> Iterator[Session]:
    """Transactional scope: commit on success, roll back on any exception."""
    session = factory()
    try:
        yield session
        session.commit()
    except BaseException:
        session.rollback()
        raise
    finally:
        session.close()
