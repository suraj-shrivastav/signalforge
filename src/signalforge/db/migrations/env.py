"""Alembic environment.

Migrations always run over the session-mode connection (ADR-0003). The URL is
read from validated settings, never from alembic.ini, so a password never lands
in a tracked file.
"""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import Connection

from signalforge.core.config import get_settings
from signalforge.db import models  # noqa: F401  (registers tables on Base.metadata)
from signalforge.db.base import Base
from signalforge.db.session import ConnectionMode, create_db_engine

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Emit SQL to stdout without connecting. Used to review a migration."""
    settings = get_settings()
    context.configure(
        url=settings.worker_database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_db_engine(get_settings(), ConnectionMode.SESSION)
    try:
        with engine.connect() as connection:
            do_run_migrations(connection)
    finally:
        engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
