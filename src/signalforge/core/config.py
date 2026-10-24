"""Application settings, loaded from the environment and validated once at startup.

Configuration is read through :func:`get_settings`. Nothing else in the codebase
reads ``os.environ`` directly, so every setting has one declared type, one
default and one place to look it up.
"""

from decimal import Decimal
from enum import StrEnum
from functools import lru_cache
from typing import Any, Self
from urllib.parse import urlparse

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
    # Secondary-source search for the research stage. Unset: no Tavily lookups.
    tavily_api_key: SecretStr | None = None
    # Optional separate endpoint for the article writer only (e.g. NVIDIA's OpenAI-compatible
    # API); every other role keeps using llm_base_url.
    llm_writer_base_url: str | None = None
    llm_writer_api_key: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices("llm_writer_api_key", "LLM_WRITER_API_KEY", "NVIDIA_API"),
    )
    llm_timeout_article_writer_s: float = Field(default=180.0, gt=0)
    llm_model_relevance: str = "openai/gpt-4o-mini"
    llm_model_topic_card: str = "openai/gpt-4o-mini"
    llm_model_research_extraction: str = "openai/gpt-4o-mini"
    llm_model_claim_embedding: str = "openai/text-embedding-3-small"
    # Writer and judge must resolve to different families (PRD FR-08); the drafting
    # stage refuses to start otherwise, so keep these defaults in separate namespaces.
    llm_model_article_writer: str = "anthropic/claude-fable-5.1"
    llm_model_claim_judge: str = "google/gemini-2.5-flash-lite"
    # Vendor-specific request fields, as JSON, merged into the request body.
    llm_extra_body: dict[str, Any] = Field(default_factory=dict)
    # Extra fields for embedding requests, e.g. NVIDIA's {"input_type": "passage"}.
    llm_embed_extra_body: dict[str, Any] = Field(default_factory=dict)
    # Output cap sent as max_tokens on every chat call. Reasoning models spend part of it
    # thinking before the reply, so it leaves room for that plus a 1000-word draft as JSON.
    llm_max_output_tokens: int = Field(default=16_384, ge=1)
    # Writer cap. A 700 to 1000 word article with per-sentence claim ids is long JSON and was
    # cut off at 6,000 tokens. Lower it for providers that reject a call (402) when the account
    # cannot afford the full cap.
    llm_max_output_tokens_article_writer: int = Field(default=12_000, ge=1)

    # Shown on every published article. Set PUBLISH_BYLINE to the editor's real name: Google
    # treats invented authors as deceptive, and asks that AI use be clear to readers.
    publish_byline: str = "SignalForge Editorial"
    publish_process_note: str = (
        "Sources were collected and checked automatically against their stored text. "
        "An editor reviewed and approved this article before it was published."
    )

    # Run research then draft in the API process right after an editor accepts a card.
    # Off by default. The cap counts research packages created in the last 24 hours, so a
    # burst of accepts cannot spend without limit.
    auto_pipeline_on_accept: bool = False
    auto_pipeline_daily_cap: int = Field(default=10, ge=1)

    # Supabase project URL. Article images are stored in its public bucket and the API only
    # accepts image URLs from this host. Leave empty to reject image attachments.
    supabase_url: str = ""

    # IndexNow: tells Bing and other participating engines about new or changed URLs.
    # Both must be set (SITE_URL matches the web app's, INDEXNOW_KEY is also served by the web
    # app at /indexnow-key.txt). Leave either empty to turn the ping off.
    site_url: str = ""
    indexnow_key: str = ""

    # PRD §12 proposed figures, to be calibrated. Decimal, not float: these are
    # compared against accumulated spend and must not drift.
    budget_per_topic_usd: Decimal = Decimal("0.50")
    budget_per_article_usd: Decimal = Decimal("1.50")

    # Temporary HTTP trigger for ingest (ADR-0005). Default off. Owner: suraj.
    # Remove when ingest runs through the queue.
    ingest_endpoint_enabled: bool = False
    ingest_token: SecretStr | None = None

    # Shared key for editor decision writes (X-Editor-Key). Unset: writes get 503.
    editor_api_key: SecretStr | None = None
    # Separate, revocable key for the automation agent (sent in the same X-Editor-Key header).
    # It opens the same write endpoints plus /agent/*. Unset: the agent has no access.
    agent_api_key: SecretStr | None = None

    # Rules the agent's automatic review applies (see signalforge/auto_review.py).
    auto_review_min_words: int = Field(default=250, ge=1)
    auto_review_min_claims: int = Field(default=3, ge=1)
    auto_review_max_flagged_share: float = Field(default=0.4, ge=0, le=1)
    auto_review_max_redrafts: int = Field(default=2, ge=0)

    @model_validator(mode="after")
    def _require_token_for_ingest_endpoint(self) -> Self:
        if self.ingest_endpoint_enabled and (
            self.ingest_token is None or not self.ingest_token.get_secret_value()
        ):
            raise ValueError("INGEST_TOKEN is required when INGEST_ENDPOINT_ENABLED is true")
        return self

    @model_validator(mode="after")
    def _require_credentials_for_live_providers(self) -> Self:
        local = urlparse(self.llm_base_url or "").hostname in {"localhost", "127.0.0.1", "::1"}
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
