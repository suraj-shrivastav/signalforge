"""Research and draft the accepted cards right after an accept, in a background task."""

import logging
import threading
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select

from apps.worker import draft, research
from signalforge.core.config import Settings
from signalforge.db.models.research import ResearchPackageRow
from signalforge.db.session import ConnectionMode, create_db_engine, create_session_factory

log = logging.getLogger(__name__)

# One pass at a time: a second accept waits, then finds nothing left to do.
_LOCK = threading.Lock()
_PASS_LIMIT = 3


def run_after_accept(settings: Settings) -> None:
    """Research the oldest accepted cards, then draft them. Never raises."""
    with _LOCK:
        engine = create_db_engine(settings, ConnectionMode.SESSION)
        try:
            since = datetime.now(UTC) - timedelta(hours=24)
            with create_session_factory(engine)() as session:
                used = session.scalar(
                    select(func.count())
                    .select_from(ResearchPackageRow)
                    .where(ResearchPackageRow.created_at >= since)
                )
            room = settings.auto_pipeline_daily_cap - (used or 0)
            if room <= 0:
                log.warning("auto pipeline skipped: daily cap reached", extra={"used": used})
                return
            researched = research.run(engine, min(_PASS_LIMIT, room))
            drafted = draft.run(engine, _PASS_LIMIT)
            log.info(
                "auto pipeline finished",
                extra={"researched": researched.researched, "drafted": drafted.drafted},
            )
        except Exception:
            log.exception("auto pipeline failed")
        finally:
            engine.dispose()
