"""Budgets are a critical path: a staged funnel only limits spend if something refuses."""

from decimal import Decimal

import pytest

from signalforge.core.budget import Budget, BudgetLimits, BudgetScope, to_usd
from signalforge.core.errors import BudgetExceededError, is_retryable


def budget(limit: str = "0.50", **caps: int) -> Budget:
    return Budget(
        scope=BudgetScope.TOPIC,
        limits=BudgetLimits(max_cost_usd=Decimal(limit), **caps),
    )


def test_a_fresh_budget_has_its_full_limit() -> None:
    assert budget("0.50").remaining_usd == Decimal("0.50")
    assert budget("0.50").is_exhausted is False


def test_recording_reduces_the_remaining_budget() -> None:
    subject = budget("0.50")

    subject.record("0.20")

    assert subject.spent_usd == Decimal("0.20")
    assert subject.remaining_usd == Decimal("0.30")
    assert subject.calls == 1


def test_costs_accumulate_without_floating_point_drift() -> None:
    """Ten cents added as 0.01 must total exactly 0.10, which floats do not guarantee."""
    subject = budget("1.00")

    for _ in range(10):
        subject.record("0.01")

    assert subject.spent_usd == Decimal("0.10")


def test_float_costs_are_rejected_rather_than_coerced() -> None:
    with pytest.raises(TypeError, match="never float"):
        to_usd(0.01)  # type: ignore[arg-type]

    with pytest.raises(TypeError):
        budget().record(0.01)  # type: ignore[arg-type]


def test_check_passes_while_there_is_headroom() -> None:
    subject = budget("0.50")
    subject.record("0.40")

    subject.check("0.10")


def test_check_raises_when_the_estimate_would_exceed_the_cap() -> None:
    subject = budget("0.50")
    subject.record("0.45")

    with pytest.raises(BudgetExceededError, match="cost budget"):
        subject.check("0.10")


def test_spending_exactly_to_the_limit_is_allowed() -> None:
    """A cap is a ceiling, not a value to stay under."""
    subject = budget("0.50")

    subject.check("0.50")
    subject.record("0.50")

    assert subject.remaining_usd == Decimal("0")
    assert subject.is_exhausted is True


def test_an_exhausted_budget_refuses_even_a_free_call() -> None:
    subject = budget("0.50")
    subject.record("0.50")

    with pytest.raises(BudgetExceededError):
        subject.check()


def test_budget_errors_are_permanent_not_retryable() -> None:
    """Retrying a call you cannot afford would loop forever (PRD §17)."""
    subject = budget("0.10")
    subject.record("0.10")

    with pytest.raises(BudgetExceededError) as caught:
        subject.check("0.01")

    assert is_retryable(caught.value) is False


def test_overspend_is_still_recorded() -> None:
    """Actual cost can exceed the estimate; hiding it would corrupt cost reporting."""
    subject = budget("0.10")

    subject.record("0.25")

    assert subject.spent_usd == Decimal("0.25")
    assert subject.remaining_usd == Decimal("0"), "remaining is floored, never negative"


def test_call_limit_stops_runaway_loops() -> None:
    subject = budget("100.00", max_calls=2)

    subject.record("0.01")
    subject.record("0.01")

    assert subject.is_exhausted is True
    with pytest.raises(BudgetExceededError, match="call budget"):
        subject.check("0.01")


def test_token_limit_stops_runaway_loops() -> None:
    subject = budget("100.00", max_tokens=1000)

    subject.record("0.01", tokens=1000)

    assert subject.is_exhausted is True
    with pytest.raises(BudgetExceededError, match="token budget"):
        subject.check("0.01")


def test_uncapped_dimensions_never_exhaust() -> None:
    subject = budget("100.00")

    for _ in range(50):
        subject.record("0.01", tokens=10_000)

    assert subject.is_exhausted is False


def test_error_context_carries_the_scope_without_leaking_anything() -> None:
    subject = Budget(scope=BudgetScope.ARTICLE, limits=BudgetLimits(max_cost_usd=Decimal("1.50")))
    subject.record("1.50")

    with pytest.raises(BudgetExceededError) as caught:
        subject.check("0.01")

    assert caught.value.context["scope"] == "article"
    assert caught.value.context["limit_usd"] == "1.50"
