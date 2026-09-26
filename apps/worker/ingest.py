"""CLI: ``uv run python -m apps.worker.ingest hackernews --hours 24``.

Runs over the session-mode connection (ADR-0003), like every worker process.
"""

import argparse
import logging
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

import httpx

from apps.worker._args import hours
from signalforge.core.config import get_settings
from signalforge.core.logging import configure_logging
from signalforge.db.session import ConnectionMode, create_db_engine, create_session_factory
from signalforge.plugins.sources import SOURCE_NAMES, USER_AGENT, build_source
from signalforge.stages.ingest import run_ingest

log = logging.getLogger(__name__)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="ingest")
    parser.add_argument("source", choices=SOURCE_NAMES)
    parser.add_argument("--hours", type=hours, default=24, help="look back this many hours")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    settings = get_settings()
    configure_logging(settings.log_level)
    engine = create_db_engine(settings, ConnectionMode.SESSION)
    try:
        with (
            httpx.Client(headers={"User-Agent": USER_AGENT}) as client,
            create_session_factory(engine)() as session,
        ):
            run_ingest(
                build_source(args.source, client),
                session,
                since=datetime.now(UTC) - timedelta(hours=args.hours),
            )
    finally:
        engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
