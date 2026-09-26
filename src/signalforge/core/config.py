"""Application settings, loaded from the environment and validated once at startup.

Configuration is read through :func:`get_settings`. Nothing else in the codebase
reads ``os.environ`` directly, so every setting has one declared type, one
default and one place to look it up.
"""

from decimal import Decimal
from enum import StrEnum
from functools import lru_cache
from typing import Any, Self

from pydantic import AliasChoices, Field, PostgresDsn, SecretStr, ValidationError, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from signalforge.core.budget import BudgetLimits, BudgetScope
from signalforge.core.errors import ConfigurationError


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

    # Registry key (llm/registry.py), validated when the gateway is built so a
    # newly registered provider needs no change here.
    llm_provider: str = "fake"
    llm_base_url: str | None = None
    # OPENROUTER_API_KEY is accepted so existing .env files keep working.
    llm_api_key: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices("llm_api_key", "LLM_API_KEY", "OPENROUTER_API_KEY"),
    )
    llm_model_relevance: str = "openai/gpt-4o-mini"
    # Vendor-specific request fields, as JSON, merged into the request body.
    llm_extra_body: dict[str, Any] = Field(default_factory=dict)

    # PRD §12 proposed figures, to be calibrated. Decimal, not float: these are
    # compared against accumulated spend and must not drift.
    budget_per_topic_usd: Decimal = Decimal("0.50")
    budget_per_article_usd: Decimal = Decimal("1.50")

    # Temporary HTTP trigger for ingest (ADR-0005). Default off. Owner: suraj.
    # Remove when ingest runs through the queue.
    ingest_endpoint_enabled: bool = False
    ingest_token: SecretStr | None = None

    @model_validator(mode="after")
    def _require_token_for_ingest_endpoint(self) -> Self:
        if self.ingest_endpoint_enabled and (
            self.ingest_token is None or not self.ingest_token.get_secret_value()
        ):
            raise ValueError("INGEST_TOKEN is required when INGEST_ENDPOINT_ENABLED is true")
        return self

    @model_validator(mode="after")
    def _require_credentials_for_live_providers(self) -> Self:
        local = any(h in (self.llm_base_url or "") for h in ("localhost", "127.0.0.1"))
        if self.llm_provider != "fake" and not local and self.llm_api_key is None:
            raise ValueError("LLM_API_KEY is required when LLM_PROVIDER is not 'fake'")
        return self

    @property
    def worker_database_url(self) -> str:
        """Session-mode connection: Procrastinate's LISTEN/NOTIFY and Alembic."""
        return str(self.database_url)

    @property
    def api_database_url(self) -> str:
        """Transaction-mode connection when configured, otherwise the session one."""
        return str(self.database_pooler_url or self.database_url)

    def budget_limits(self, scope: BudgetScope) -> BudgetLimits:
        """Configured caps for a scope, so limits live in config rather than in stages."""
        caps = {
            BudgetScope.TOPIC: self.budget_per_topic_usd,
            BudgetScope.ARTICLE: self.budget_per_article_usd,
        }
        return BudgetLimits(max_cost_usd=caps[scope])


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
