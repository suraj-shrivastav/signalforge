"""CLI: ``uv run python -m apps.worker.research --limit 10``."""

import argparse
import logging
from collections.abc import Sequence

import httpx
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from apps.worker._args import bounded_limit
from signalforge.core.budget import Budget, BudgetScope
from signalforge.core.config import Settings, get_settings
from signalforge.core.logging import configure_logging
from signalforge.core.protocols import SearchProvider, SearchResult
from signalforge.db.session import ConnectionMode, create_db_engine, create_session_factory
from signalforge.llm.gateway import LLMGateway, build_gateway
from signalforge.plugins.search.direct_fetch import DirectFetcher
from signalforge.plugins.search.tavily import TavilyClient
from signalforge.stages.research import ResearchResult, run_research

log = logging.getLogger(__name__)

MAX_LIMIT = 50


class NoSecondarySearch:
    """Stand-in when TAVILY_API_KEY is unset: research uses the primary source only."""

    def search(self, query: str, *, max_results: int) -> list[SearchResult]:  # noqa: ARG002
        return []


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="research")
    parser.add_argument(
        "--limit", type=bounded_limit(MAX_LIMIT), default=10, help="max cards to research"
    )
    parser.add_argument(
        "--retry-failed",
        action="store_true",
        help="re-research cards whose package failed or needed more info; the row is replaced",
    )
    return parser.parse_args(argv)


def build_search(settings: Settings, client: httpx.Client) -> SearchProvider:
    if settings.tavily_api_key is None or not settings.tavily_api_key.get_secret_value():
        log.warning("TAVILY_API_KEY unset: research runs on primary sources only")
        return NoSecondarySearch()
    return TavilyClient(client, api_key=settings.tavily_api_key.get_secret_value())


def run(engine: Engine, limit: int, *, retry_failed: bool = False) -> ResearchResult:
    """Run one research pass on ``engine`` (caller owns the engine)."""
    settings = get_settings()

    def gateway_factory(session: Session, budget: Budget) -> LLMGateway:
        return build_gateway(settings, session, budget)

    with httpx.Client() as client, create_session_factory(engine)() as session:
        return run_research(
            session,
            gateway_factory,
            DirectFetcher(client),
            build_search(settings, client),
            budget_limits=settings.budget_limits(BudgetScope.TOPIC),
            limit=limit,
            retry_failed=retry_failed,
        )


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    settings = get_settings()
    configure_logging(settings.log_level)
    engine = create_db_engine(settings, ConnectionMode.SESSION)
    try:
        result = run(engine, args.limit, retry_failed=args.retry_failed)
    finally:
        engine.dispose()
    print(
        f"considered={result.considered} researched={result.researched} "
        f"needs_more_info={result.needs_more_info} failed={result.failed}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
