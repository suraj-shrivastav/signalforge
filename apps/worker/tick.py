"""CLI: ``uv run python -m apps.worker.tick`` (cron entry point).

Ingests every source, then assesses. One failing source never stops the rest.
Exit code 0 if at least one source ingested, else 1. Assess is still attempted
when all sources failed (there may be unassessed signals from earlier runs).
"""

import argparse
import logging
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

import httpx

from apps.worker import assess
from apps.worker.ingest import MAX_HOURS, _hours
from signalforge.core.config import get_settings
from signalforge.core.logging import configure_logging
from signalforge.db.session import ConnectionMode, create_db_engine, create_session_factory
from signalforge.plugins.sources import SOURCE_NAMES, USER_AGENT, build_source
from signalforge.stages.ingest import run_ingest

log = logging.getLogger(__name__)


def _limit(value: str) -> int:
    limit = int(value)
    if not 1 <= limit <= 500:
        raise argparse.ArgumentTypeError("must be between 1 and 500")
    return limit


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="tick")
    parser.add_argument(
        "--hours", type=_hours, default=24, help=f"look back hours (1..{MAX_HOURS})"
    )
    parser.add_argument("--assess-limit", type=_limit, default=25, help="max signals to assess")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    settings = get_settings()
    configure_logging(settings.log_level)
    engine = create_db_engine(settings, ConnectionMode.SESSION)
    succeeded = 0
    since = datetime.now(UTC) - timedelta(hours=args.hours)
    try:
        with httpx.Client(headers={"User-Agent": USER_AGENT}, follow_redirects=True) as client:
            for name in SOURCE_NAMES:
                try:
                    with create_session_factory(engine)() as session:
                        result = run_ingest(build_source(name, client), session, since=since)
                except Exception:
                    log.exception("ingest failed for source %s", name)
                    print(f"{name}: FAILED")
                    continue
                succeeded += 1
                print(f"{name}: fetched={result.fetched} inserted={result.inserted}")
        if settings.llm_provider == "fake":
            log.info("assess skipped: LLM_PROVIDER is fake")
            print("assess: skipped (fake provider)")
        else:
            try:
                res = assess.run(engine, args.assess_limit)
                print(
                    f"assess: considered={res.considered} assessed={res.assessed} "
                    f"relevant={res.relevant} failed={res.failed}"
                )
            except Exception:
                log.exception("assess failed")
                print("assess: FAILED")
    finally:
        engine.dispose()
    return 0 if succeeded else 1


if __name__ == "__main__":
    raise SystemExit(main())
