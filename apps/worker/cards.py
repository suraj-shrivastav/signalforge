"""CLI: ``uv run python -m apps.worker.cards --limit 25``."""

import argparse
import logging
from collections.abc import Sequence

from sqlalchemy import Engine
from sqlalchemy.orm import Session

from apps.worker._args import bounded_limit
from signalforge.core.budget import Budget, BudgetScope
from signalforge.core.config import get_settings
from signalforge.core.logging import configure_logging
from signalforge.db.session import ConnectionMode, create_db_engine, create_session_factory
from signalforge.llm.gateway import LLMGateway, build_gateway
from signalforge.stages.cards import CardsResult, run_cards

log = logging.getLogger(__name__)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="cards")
    parser.add_argument("--limit", type=bounded_limit(200), default=25, help="max signals to card")
    return parser.parse_args(argv)


def run(engine: Engine, limit: int) -> CardsResult:
    """Run one cards pass on ``engine`` (caller owns the engine)."""
    settings = get_settings()

    def gateway_factory(session: Session) -> LLMGateway:
        budget = Budget(BudgetScope.TOPIC, settings.budget_limits(BudgetScope.TOPIC))
        return build_gateway(settings, session, budget)

    with create_session_factory(engine)() as session:
        return run_cards(session, gateway_factory, limit=limit)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    settings = get_settings()
    configure_logging(settings.log_level)
    engine = create_db_engine(settings, ConnectionMode.SESSION)
    try:
        result = run(engine, args.limit)
    finally:
        engine.dispose()
    print(
        f"considered={result.considered} created={result.created} "
        f"failed={result.failed} stopped_on_budget={result.stopped_on_budget}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
