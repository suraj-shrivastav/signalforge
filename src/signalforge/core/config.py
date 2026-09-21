"""Application settings, loaded from the environment and validated once at startup.

Configuration is read through :func:`get_settings`. Nothing else in the codebase
reads ``os.environ`` directly, so every setting has one declared type, one
default and one place to look it up.
"""

from enum import StrEnum
from functools import lru_cache
from typing import Literal, Self

from pydantic import AliasChoices, Field, PostgresDsn, SecretStr, ValidationError, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from signalforge.core.errors import ConfigurationError

LLMProviderName = Literal["fake", "openrouter"]


class Environment(StrEnum):
    LOCAL = "local"
    CI = "ci"
    PRODUCTION = "production"


class Settings(BaseSettings):
    """Validated application settings. Immutable once constructed."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        frozen=True,
    )

    environment: Environment = Environment.LOCAL
    log_level: str = "INFO"

    # Session-mode connection. The worker needs LISTEN/NOTIFY and Alembic needs a
    # stable session, neither of which survives transaction pooling. See ADR-0003.
    # SUPABASE_DB_STRING is accepted so existing .env files keep working, but the
    # canonical name is vendor-neutral.
    database_url: PostgresDsn = Field(
        validation_alias=AliasChoices("DATABASE_URL", "SUPABASE_DB_STRING"),
    )

    # Optional transaction-mode connection (port 6543) for the API's short
    # transactions. Prepared statements must be disabled on it.
    database_pooler_url: PostgresDsn | None = None

    llm_provider: LLMProviderName = "fake"
    openrouter_api_key: SecretStr | None = None

    @model_validator(mode="after")
    def _require_credentials_for_live_providers(self) -> Self:
        if self.llm_provider == "openrouter" and self.openrouter_api_key is None:
            raise ValueError("OPENROUTER_API_KEY is required when LLM_PROVIDER is 'openrouter'")
        return self

    @property
    def worker_database_url(self) -> str:
        """Session-mode connection: Procrastinate's LISTEN/NOTIFY and Alembic."""
        return str(self.database_url)

    @property
    def api_database_url(self) -> str:
        """Transaction-mode connection when configured, otherwise the session one."""
        return str(self.database_pooler_url or self.database_url)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Load and validate settings once per process.

    Raises:
        ConfigurationError: if any setting is missing or malformed. Raised as a
            permanent error so startup fails loudly rather than degrading.
    """
    try:
        return Settings()  # type: ignore[call-arg]  # pydantic-settings fills from env
    except ValidationError as exc:
        raise ConfigurationError(
            "Invalid application configuration; check your .env against .env.example",
            context={"error_count": exc.error_count()},
        ) from exc
