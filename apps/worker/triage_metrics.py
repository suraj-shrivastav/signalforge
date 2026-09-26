"""CLI: ``uv run python -m apps.worker.triage_metrics --days 14`` (read only)."""

import argparse
import logging
import math
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from apps.worker._args import days as days_arg
from signalforge.core.config import get_settings
from signalforge.core.logging import configure_logging
from signalforge.db.repositories.cards import CardRepository
from signalforge.db.session import ConnectionMode, create_db_engine, create_session_factory

log = logging.getLogger(__name__)

Decision = tuple[str, Sequence[str], int | None]


@dataclass(frozen=True)
class Metrics:
    cards_created: int
    decided: int
    accept_rate: float | None
    snooze_rate: float | None
    median_ms: float | None
    p90_ms: float | None
    reason_tags: dict[str, int]
    waiting: int


def percentile(values: Sequence[int], pct: float) -> float | None:
    """Nearest-rank percentile; None for an empty input."""
    if not values:
        return None
    ordered = sorted(values)
    rank = max(1, math.ceil(pct / 100 * len(ordered)))
    return float(ordered[rank - 1])


def median(values: Sequence[int]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return float(ordered[mid])
    return (ordered[mid - 1] + ordered[mid]) / 2


def compute_metrics(cards_created: int, decisions: Sequence[Decision], waiting: int) -> Metrics:
    """``decisions`` holds the latest decision per card."""
    decided = len(decisions)
    accepted = sum(1 for d, _, _ in decisions if d == "accepted")
    snoozed = sum(1 for d, _, _ in decisions if d == "snoozed")
    times = [ms for _, _, ms in decisions if ms is not None]
    tags: Counter[str] = Counter()
    for _, reasons, _ in decisions:
        tags.update(reasons)
    return Metrics(
        cards_created=cards_created,
        decided=decided,
        accept_rate=accepted / decided if decided else None,
        snooze_rate=snoozed / decided if decided else None,
        median_ms=median(times),
        p90_ms=percentile(times, 90),
        reason_tags=dict(sorted(tags.items())),
        waiting=waiting,
    )


def _fmt_rate(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.2f}"


def _fmt_ms(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.0f}"


def format_metrics(m: Metrics) -> str:
    tags = " ".join(f"{k}={v}" for k, v in m.reason_tags.items()) or "none"
    return "\n".join(
        [
            f"cards_created={m.cards_created}",
            f"decided={m.decided}",
            f"accept_rate={_fmt_rate(m.accept_rate)}",
            f"snooze_rate={_fmt_rate(m.snooze_rate)}",
            f"median_ms={_fmt_ms(m.median_ms)}",
            f"p90_ms={_fmt_ms(m.p90_ms)}",
            f"reason_tags: {tags}",
            f"waiting={m.waiting}",
        ]
    )


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="triage_metrics")
    parser.add_argument("--days", type=days_arg, default=14, help="window in days (1..90)")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    settings = get_settings()
    configure_logging(settings.log_level)
    engine = create_db_engine(settings, ConnectionMode.SESSION)
    since = datetime.now(UTC) - timedelta(days=args.days)
    try:
        with create_session_factory(engine)() as session:
            stats = CardRepository(session).decision_stats(since)
    finally:
        engine.dispose()
    print(format_metrics(compute_metrics(stats.cards_created, stats.decisions, stats.waiting)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
