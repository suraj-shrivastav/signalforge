"""Cost, call and token budgets.

A staged funnel only controls spend if something refuses to spend (PRD §17). A
budget is checked *before* a call and recorded *after*, so an exhausted budget
stops work rather than discovering the overspend afterwards.

Money is :class:`~decimal.Decimal` throughout. ``float`` is rejected rather than
coerced: repeatedly adding fractions of a cent in binary floating point drifts,
and these totals are compared against a hard limit and written to a
``Numeric(12, 6)`` column.

Not thread-safe by design. A budget belongs to one topic or article being
processed by one worker; sharing one across threads would make the check racy.
"""

from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum

from signalforge.core.errors import BudgetExceededError

ZERO = Decimal("0")


class BudgetScope(StrEnum):
    TOPIC = "topic"
    ARTICLE = "article"


def to_usd(amount: Decimal | int | str) -> Decimal:
    """Convert to Decimal, refusing ``float``.

    Raises:
        TypeError: if given a float, which cannot represent cents exactly.
    """
    if isinstance(amount, float):
        raise TypeError("Costs must be Decimal, int or str, never float: use Decimal('0.01')")
    return Decimal(amount)


@dataclass(frozen=True)
class BudgetLimits:
    """Caps for one scope. ``None`` means that dimension is not capped."""

    max_cost_usd: Decimal
    max_calls: int | None = None
    max_tokens: int | None = None


@dataclass
class Budget:
    """Tracks spend for one scope against its limits."""

    scope: BudgetScope
    limits: BudgetLimits
    spent_usd: Decimal = field(default=ZERO)
    calls: int = 0
    tokens: int = 0

    @property
    def remaining_usd(self) -> Decimal:
        """Headroom left, floored at zero so callers never see a negative budget."""
        return max(ZERO, self.limits.max_cost_usd - self.spent_usd)

    @property
    def is_exhausted(self) -> bool:
        return self.remaining_usd == ZERO or self._hit_call_limit() or self._hit_token_limit()

    def _hit_call_limit(self) -> bool:
        return self.limits.max_calls is not None and self.calls >= self.limits.max_calls

    def _hit_token_limit(self) -> bool:
        return self.limits.max_tokens is not None and self.tokens >= self.limits.max_tokens

    def would_exceed(self, estimated_cost_usd: Decimal | int | str) -> bool:
        return self.spent_usd + to_usd(estimated_cost_usd) > self.limits.max_cost_usd

    def check(self, estimated_cost_usd: Decimal | int | str = ZERO) -> None:
        """Assert there is room for a call before making it.

        Raises:
            BudgetExceededError: permanent, so the pipeline stops instead of
                retrying a call it cannot afford.
        """
        if self._hit_call_limit():
            raise BudgetExceededError(
                f"{self.scope} call budget exhausted",
                context={"scope": str(self.scope), "calls": self.calls},
            )
        if self._hit_token_limit():
            raise BudgetExceededError(
                f"{self.scope} token budget exhausted",
                context={"scope": str(self.scope), "tokens": self.tokens},
            )
        # The `remaining == 0` arm matters: a fully spent budget must refuse even a
        # zero-cost call, otherwise `check()` with no estimate would wave it through.
        if self.remaining_usd == ZERO or self.would_exceed(estimated_cost_usd):
            raise BudgetExceededError(
                f"{self.scope} cost budget exhausted",
                context={
                    "scope": str(self.scope),
                    "spent_usd": str(self.spent_usd),
                    "limit_usd": str(self.limits.max_cost_usd),
                },
            )

    def record(self, cost_usd: Decimal | int | str, *, tokens: int = 0) -> None:
        """Record actual usage after a call. Always recorded, even when it overran."""
        self.spent_usd += to_usd(cost_usd)
        self.calls += 1
        self.tokens += tokens
