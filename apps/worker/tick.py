"""CLI: ``uv run python -m apps.worker.tick`` (cron entry point).

Ingests every source, then assesses, then builds topic cards. One failing
source or stage never stops the later ones. Assess and cards are still attempted
when all sources failed (there may be a backlog).
Exit codes: 0 = at least one source ingested and assess/cards ok or skipped;
1 = every source failed (even if assess or cards also failed);
2 = ingest ok but assess or cards failed.
"""

import argparse
import logging
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

import httpx

from apps.worker import assess, cards
from apps.worker._args import MAX_HOURS, bounded_limit, hours, limit
from signalforge.core.config import get_settings
from signalforge.core.logging import configure_logging
from signalforge.db.session import ConnectionMode, create_db_engine, create_session_factory
from signalforge.plugins.sources import SOURCE_NAMES, USER_AGENT, build_source
from signalforge.stages.ingest import run_ingest

log = logging.getLogger(__name__)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="tick")
    parser.add_argument("--hours", type=hours, default=24, help=f"look back hours (1..{MAX_HOURS})")
    parser.add_argument("--assess-limit", type=limit, default=25, help="max signals to assess")
    parser.add_argument(
        "--cards-limit", type=bounded_limit(200), default=25, help="max signals to card (1..200)"
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    settings = get_settings()
    configure_logging(settings.log_level)
    engine = create_db_engine(settings, ConnectionMode.SESSION)
    succeeded = 0
    stage_failed = False
    since = datetime.now(UTC) - timedelta(hours=args.hours)
    session_factory = create_session_factory(engine)
    try:
        with httpx.Client(headers={"User-Agent": USER_AGENT}, follow_redirects=True) as client:
            for name in SOURCE_NAMES:
                try:
                    with session_factory() as session:
                        result = run_ingest(build_source(name, client), session, since=since)
                except Exception as exc:
                    log.exception("ingest failed for source %s", name)
                    print(f"{name}: FAILED ({type(exc).__name__})")
                    continue
                succeeded += 1
                print(f"{name}: fetched={result.fetched} inserted={result.inserted}")
        if settings.llm_provider == "fake":
            log.info("assess skipped: LLM_PROVIDER is fake")
            print("assess: skipped (fake provider)")
            log.info("cards skipped: LLM_PROVIDER is fake")
            print("cards: skipped (fake provider)")
        else:
            try:
                res = assess.run(engine, args.assess_limit)
                print(
                    f"assess: considered={res.considered} assessed={res.assessed} "
                    f"relevant={res.relevant} failed={res.failed} "
                    f"stopped_on_budget={res.stopped_on_budget}"
                )
            except Exception:
                stage_failed = True
                log.exception("assess failed")
                print("assess: FAILED")
            try:
                made = cards.run(engine, args.cards_limit)
                print(
                    f"cards: considered={made.considered} created={made.created} "
                    f"failed={made.failed} stopped_on_budget={made.stopped_on_budget}"
                )
            except Exception:
                stage_failed = True
                log.exception("cards failed")
                print("cards: FAILED")
    finally:
        engine.dispose()
    if not succeeded:
        return 1
    return 2 if stage_failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
