"""CLI: ``uv run python -m apps.worker.draft --limit 10``."""

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
from signalforge.stages.draft import DraftResult, run_draft

log = logging.getLogger(__name__)

MAX_LIMIT = 50


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="draft")
    parser.add_argument(
        "--limit", type=bounded_limit(MAX_LIMIT), default=10, help="max cards to draft"
    )
    parser.add_argument(
        "--retry-failed",
        action="store_true",
        help="redraft cards whose draft failed; the failed row is replaced",
    )
    parser.add_argument(
        "--revise",
        action="store_true",
        help="redraft drafts the editor sent back, using the editor's note",
    )
    return parser.parse_args(argv)


def run(
    engine: Engine, limit: int, *, retry_failed: bool = False, revise: bool = False
) -> DraftResult:
    """Run one draft pass on ``engine`` (caller owns the engine)."""
    settings = get_settings()

    def gateway_factory(session: Session, budget: Budget) -> LLMGateway:
        return build_gateway(settings, session, budget)

    with create_session_factory(engine)() as session:
        return run_draft(
            session,
            gateway_factory,
            budget_limits=settings.budget_limits(BudgetScope.ARTICLE),
            limit=limit,
            retry_failed=retry_failed,
            revise=revise,
        )


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    settings = get_settings()
    configure_logging(settings.log_level)
    engine = create_db_engine(settings, ConnectionMode.SESSION)
    try:
        result = run(engine, args.limit, retry_failed=args.retry_failed, revise=args.revise)
    finally:
        engine.dispose()
    print(
        f"considered={result.considered} drafted={result.drafted} "
        f"needs_more_info={result.needs_more_info} failed={result.failed}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
