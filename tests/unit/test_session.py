"""Engine construction rules. No network: only the options we would pass are checked."""

from typing import Any

import pytest

from signalforge.core.config import Settings
from signalforge.core.errors import ConfigurationError
from signalforge.db.session import (
    ConnectionMode,
    create_session_factory,
    engine_options,
    normalise_dsn,
    session_scope,
)

SESSION_DSN = "postgresql://postgres.ref:pw@aws-0-ap-south-1.pooler.supabase.com:5432/postgres"
POOLER_DSN = "postgresql://postgres.ref:pw@aws-0-ap-south-1.pooler.supabase.com:6543/postgres"


def build(**overrides: Any) -> Settings:
    values: dict[str, Any] = {"database_url": SESSION_DSN, **overrides}
    return Settings(_env_file=None, **values)  # type: ignore[call-arg]


def test_bare_scheme_is_pinned_to_psycopg3() -> None:
    """Without this SQLAlchemy loads psycopg2, which is not a dependency."""
    assert normalise_dsn(SESSION_DSN).startswith("postgresql+psycopg://")


def test_an_explicit_driver_is_left_alone() -> None:
    dsn = "postgresql+asyncpg://user:pw@host:5432/db"

    assert normalise_dsn(dsn) == dsn


def test_a_url_without_a_scheme_is_a_configuration_error() -> None:
    with pytest.raises(ConfigurationError):
        normalise_dsn("host:5432/db")


def test_session_mode_keeps_prepared_statements() -> None:
    options = engine_options(build(), ConnectionMode.SESSION)

    assert "connect_args" not in options
    assert ":5432" in options["url"]


def test_transaction_mode_disables_prepared_statements() -> None:
    """Supavisor cannot keep prepared statements across pooled transactions."""
    options = engine_options(build(database_pooler_url=POOLER_DSN), ConnectionMode.TRANSACTION)

    assert options["connect_args"]["prepare_threshold"] is None
    assert ":6543" in options["url"]


def test_transaction_mode_does_not_overflow_the_external_pool() -> None:
    options = engine_options(build(database_pooler_url=POOLER_DSN), ConnectionMode.TRANSACTION)

    assert options["max_overflow"] == 0


def test_both_modes_pre_ping() -> None:
    """Pooled connections can be closed server-side between checkouts."""
    for mode in ConnectionMode:
        assert engine_options(build(), mode)["pool_pre_ping"] is True


class RecordingSession:
    """Records the lifecycle calls session_scope makes, in order."""

    def __init__(self, calls: list[str]) -> None:
        self.calls = calls

    def commit(self) -> None:
        self.calls.append("commit")

    def rollback(self) -> None:
        self.calls.append("rollback")

    def close(self) -> None:
        self.calls.append("close")


def test_session_scope_commits_then_closes_on_success() -> None:
    calls: list[str] = []

    with session_scope(lambda: RecordingSession(calls)):  # type: ignore[arg-type]
        pass

    assert calls == ["commit", "close"]


def test_session_scope_rolls_back_and_closes_on_error() -> None:
    calls: list[str] = []

    with pytest.raises(RuntimeError), session_scope(lambda: RecordingSession(calls)):  # type: ignore[arg-type]
        raise RuntimeError("boom")

    assert calls == ["rollback", "close"]


def test_session_factory_does_not_expire_on_commit() -> None:
    """Artifacts are read after commit; expiring would trigger surprise queries."""
    factory = create_session_factory(object())  # type: ignore[arg-type]

    assert factory.kw["expire_on_commit"] is False
