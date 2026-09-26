"""CLI: ``uv run python -m apps.worker.assess --limit 25``."""

import argparse
import logging
from collections.abc import Sequence

from sqlalchemy import Engine
from sqlalchemy.orm import Session

from signalforge.core.budget import Budget, BudgetScope
from signalforge.core.config import get_settings
from signalforge.core.logging import configure_logging
from signalforge.db.session import ConnectionMode, create_db_engine, create_session_factory
from signalforge.llm.gateway import LLMGateway, build_gateway
from signalforge.stages.assess import AssessResult, run_assess

log = logging.getLogger(__name__)


def _limit(value: str) -> int:
    limit = int(value)
    if not 1 <= limit <= 500:
        raise argparse.ArgumentTypeError("must be between 1 and 500")
    return limit


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="assess")
    parser.add_argument("--limit", type=_limit, default=25, help="max signals to assess")
    return parser.parse_args(argv)


def run(engine: Engine, limit: int) -> AssessResult:
    """Run one assess pass on ``engine`` (caller owns the engine)."""
    settings = get_settings()

    def gateway_factory(session: Session) -> LLMGateway:
        budget = Budget(BudgetScope.TOPIC, settings.budget_limits(BudgetScope.TOPIC))
        return build_gateway(settings, session, budget)

    with create_session_factory(engine)() as session:
        return run_assess(session, gateway_factory, limit=limit)


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
        f"considered={result.considered} assessed={result.assessed} "
        f"relevant={result.relevant} failed={result.failed} "
        f"stopped_on_budget={result.stopped_on_budget}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
