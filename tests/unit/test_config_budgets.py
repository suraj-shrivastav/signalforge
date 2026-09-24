"""Budget caps come from config, so they are tunable without touching stage code."""

from decimal import Decimal
from typing import Any

from signalforge.core.budget import BudgetScope
from signalforge.core.config import Settings

SESSION_DSN = "postgresql://postgres.ref:pw@aws-0-ap-south-1.pooler.supabase.com:5432/postgres"


def build(**overrides: Any) -> Settings:
    values: dict[str, Any] = {"database_url": SESSION_DSN, **overrides}
    return Settings(_env_file=None, **values)  # type: ignore[call-arg]


def test_defaults_match_the_prd_figures() -> None:
    settings = build()

    assert settings.budget_per_topic_usd == Decimal("0.50")
    assert settings.budget_per_article_usd == Decimal("1.50")


def test_limits_are_resolved_per_scope() -> None:
    settings = build()

    assert settings.budget_limits(BudgetScope.TOPIC).max_cost_usd == Decimal("0.50")
    assert settings.budget_limits(BudgetScope.ARTICLE).max_cost_usd == Decimal("1.50")


def test_caps_are_overridable_from_the_environment() -> None:
    settings = build(budget_per_article_usd="2.25")

    assert settings.budget_limits(BudgetScope.ARTICLE).max_cost_usd == Decimal("2.25")


def test_caps_stay_exact_decimals() -> None:
    """A float cap would defeat the point of Decimal accumulation."""
    assert isinstance(build(budget_per_topic_usd="0.33").budget_per_topic_usd, Decimal)
