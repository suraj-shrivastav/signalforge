"""CLI: ``uv run python -m apps.worker.tick`` (cron entry point).

Ingests every source, then assesses, builds topic cards, researches accepted
cards and drafts researched ones. One failing source or stage never stops the
later ones. The LLM stages are still attempted when all sources failed (there
may be a backlog).
Exit codes: 0 = at least one source ingested and every LLM stage ok or skipped;
1 = every source failed (even if an LLM stage also failed);
2 = ingest ok but an LLM stage failed.
"""

import argparse
import logging
from collections.abc import Callable, Sequence
from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy import Engine

from apps.worker import assess, cards, draft, research
from apps.worker._args import MAX_HOURS, bounded_limit, hours, limit
from signalforge.core.config import get_settings
from signalforge.core.logging import configure_logging
from signalforge.db.session import ConnectionMode, create_db_engine, create_session_factory
from signalforge.plugins.sources import SOURCE_NAMES, USER_AGENT, build_source
from signalforge.stages.ingest import run_ingest
from signalforge.verticals.config import load_vertical, source_enabled

log = logging.getLogger(__name__)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="tick")
    parser.add_argument("--hours", type=hours, default=24, help=f"look back hours (1..{MAX_HOURS})")
    parser.add_argument("--assess-limit", type=limit, default=25, help="max signals to assess")
    parser.add_argument(
        "--cards-limit", type=bounded_limit(200), default=25, help="max signals to card (1..200)"
    )
    parser.add_argument(
        "--research-limit",
        type=bounded_limit(research.MAX_LIMIT),
        default=1,
        help=f"max accepted cards to research, best first (1..{research.MAX_LIMIT})",
    )
    parser.add_argument(
        "--draft-limit",
        type=bounded_limit(draft.MAX_LIMIT),
        default=10,
        help=f"max researched cards to draft (1..{draft.MAX_LIMIT})",
    )
    return parser.parse_args(argv)


def _llm_stages(engine: Engine, args: argparse.Namespace) -> list[tuple[str, Callable[[], str]]]:
    """LLM stages in pipeline order; each returns its one-line summary."""

    def run_assess() -> str:
        r = assess.run(engine, args.assess_limit)
        return (
            f"considered={r.considered} assessed={r.assessed} relevant={r.relevant} "
            f"failed={r.failed} stopped_on_budget={r.stopped_on_budget}"
        )

    def run_cards() -> str:
        r = cards.run(engine, args.cards_limit)
        return (
            f"considered={r.considered} created={r.created} failed={r.failed} "
            f"stopped_on_budget={r.stopped_on_budget}"
        )

    def run_research() -> str:
        r = research.run(engine, args.research_limit)
        return (
            f"considered={r.considered} researched={r.researched} "
            f"needs_more_info={r.needs_more_info} failed={r.failed}"
        )

    def run_draft() -> str:
        r = draft.run(engine, args.draft_limit)
        return (
            f"considered={r.considered} drafted={r.drafted} "
            f"needs_more_info={r.needs_more_info} failed={r.failed}"
        )

    return [
        ("assess", run_assess),
        ("cards", run_cards),
        ("research", run_research),
        ("draft", run_draft),
    ]


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    settings = get_settings()
    configure_logging(settings.log_level)
    engine = create_db_engine(settings, ConnectionMode.SESSION)
    vertical_cfg = load_vertical()
    succeeded = 0
    stage_failed = False
    since = datetime.now(UTC) - timedelta(hours=args.hours)
    session_factory = create_session_factory(engine)
    try:
        with httpx.Client(headers={"User-Agent": USER_AGENT}, follow_redirects=True) as client:
            for name in SOURCE_NAMES:
                if not source_enabled(vertical_cfg, name):
                    print(f"{name}: disabled in vertical config")
                    continue
                try:
                    with session_factory() as session:
                        source = build_source(name, client, cfg=vertical_cfg)
                        result = run_ingest(source, session, since=since)
                except Exception as exc:
                    log.exception("ingest failed for source %s", name)
                    print(f"{name}: FAILED ({type(exc).__name__})")
                    continue
                succeeded += 1
                print(f"{name}: fetched={result.fetched} inserted={result.inserted}")
        for name, step in _llm_stages(engine, args):
            if settings.llm_provider == "fake":
                log.info("%s skipped: LLM_PROVIDER is fake", name)
                print(f"{name}: skipped (fake provider)")
                continue
            try:
                print(f"{name}: {step()}")
            except Exception:
                stage_failed = True
                log.exception("%s failed", name)
                print(f"{name}: FAILED")
    finally:
        engine.dispose()
    if not succeeded:
        return 1
    return 2 if stage_failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
