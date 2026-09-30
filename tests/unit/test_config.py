"""Config is a critical path: a bad value must fail startup, never degrade silently."""

from typing import Any

import pytest
from pydantic import ValidationError

from signalforge.core.config import Environment, Settings, get_settings
from signalforge.core.errors import ConfigurationError, is_retryable
from signalforge.llm.roles import build_roles

SESSION_DSN = "postgresql://postgres.ref:pw@aws-0-eu-west-2.pooler.supabase.com:5432/postgres"
POOLER_DSN = "postgresql://postgres.ref:pw@aws-0-eu-west-2.pooler.supabase.com:6543/postgres"


def build(**overrides: Any) -> Settings:
    """Construct settings from explicit values, ignoring any real .env on disk."""
    values: dict[str, Any] = {"database_url": SESSION_DSN, **overrides}
    return Settings(_env_file=None, **values)  # type: ignore[call-arg]


@pytest.fixture(autouse=True)
def _clear_settings_cache() -> None:
    get_settings.cache_clear()


def test_defaults_are_local_and_fake() -> None:
    settings = build()

    assert settings.environment is Environment.LOCAL
    assert settings.llm_provider == "fake"
    assert settings.llm_api_key is None
    assert settings.tavily_api_key is None


def test_tavily_key_reads_its_plain_env_name(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", SESSION_DSN)
    monkeypatch.setenv("TAVILY_API_KEY", "test-key")

    settings = Settings(_env_file=None)  # type: ignore[call-arg]

    assert settings.tavily_api_key is not None
    assert settings.tavily_api_key.get_secret_value() == "test-key"
    assert "test-key" not in repr(settings)


def test_research_extraction_role_uses_configured_model() -> None:
    spec = build_roles(build(llm_model_research_extraction="acme/extract"))["research_extraction"]

    assert (spec.model_id, spec.family) == ("acme/extract", "acme")


def test_worker_always_uses_the_session_connection() -> None:
    settings = build(database_pooler_url=POOLER_DSN)

    assert ":5432" in settings.worker_database_url


def test_api_prefers_the_pooler_when_configured() -> None:
    settings = build(database_pooler_url=POOLER_DSN)

    assert ":6543" in settings.api_database_url


def test_api_falls_back_to_the_session_connection() -> None:
    assert build().api_database_url == build().worker_database_url


def test_database_url_is_required(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_DB_STRING", raising=False)

    with pytest.raises(ValidationError, match="DATABASE_URL"):
        Settings(_env_file=None)  # type: ignore[call-arg]


def test_supabase_db_string_is_accepted_as_an_alias(monkeypatch: pytest.MonkeyPatch) -> None:
    """Existing .env files use the vendor name; the app's canonical name is DATABASE_URL."""
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("SUPABASE_DB_STRING", SESSION_DSN)

    assert Settings(_env_file=None).worker_database_url.startswith("postgresql://")  # type: ignore[call-arg]


def test_live_provider_requires_a_key() -> None:
    with pytest.raises(ValidationError, match="LLM_API_KEY"):
        build(llm_provider="openai_compatible")


def test_live_provider_accepts_a_key() -> None:
    settings = build(llm_provider="openai_compatible", llm_api_key="sk-test")

    assert settings.llm_api_key is not None
    assert settings.llm_api_key.get_secret_value() == "sk-test"


def test_secrets_are_not_exposed_by_repr() -> None:
    """SecretStr keeps keys out of logs and tracebacks."""
    settings = build(llm_provider="openai_compatible", llm_api_key="sk-leaky")

    assert "sk-leaky" not in repr(settings)


def test_settings_are_immutable() -> None:
    settings = build()

    with pytest.raises(ValidationError):
        settings.log_level = "DEBUG"


def test_unknown_env_vars_are_ignored() -> None:
    """Supabase auth keys live in .env for the dashboard; they must not break startup."""
    assert build(SUPABASE_PUBLISHABLE_KEY="whatever").log_level == "INFO"


def test_invalid_config_raises_a_permanent_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """os.environ wins over .env, so this exercises the real failure path."""
    monkeypatch.setenv("DATABASE_URL", "not-a-postgres-dsn")

    with pytest.raises(ConfigurationError) as caught:
        get_settings()

    assert is_retryable(caught.value) is False
    assert "not-a-postgres-dsn" not in str(caught.value)


def test_local_base_url_needs_no_key() -> None:
    settings = build(llm_provider="openai_compatible", llm_base_url="http://localhost:11434/v1")
    assert settings.llm_api_key is None


def test_openrouter_key_name_is_an_accepted_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", SESSION_DSN)
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-old")

    settings = Settings(_env_file=None)  # type: ignore[call-arg]

    assert settings.llm_api_key is not None
    assert settings.llm_api_key.get_secret_value() == "sk-old"


def test_extra_body_parses_from_json_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", SESSION_DSN)
    monkeypatch.setenv("LLM_EXTRA_BODY", '{"provider": {"require_parameters": true}}')

    settings = Settings(_env_file=None)  # type: ignore[call-arg]

    assert settings.llm_extra_body == {"provider": {"require_parameters": True}}
