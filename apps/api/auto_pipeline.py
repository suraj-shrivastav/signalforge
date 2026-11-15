"""Research and draft the accepted cards right after an accept, in a background task."""

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select

from apps.api import agent_runs
from apps.worker import draft, research
from signalforge.control_policy import is_paused
from signalforge.core.config import Settings
from signalforge.db.models.research import ResearchPackageRow
from signalforge.db.repositories.controls import ControlsRepository
from signalforge.db.session import ConnectionMode, create_db_engine, create_session_factory

log = logging.getLogger(__name__)

# One card per pass, best first. A second accept waits for the pipeline slot (shared with the
# agent's runs, so nothing runs in parallel) and then takes the next best card.
_PASS_LIMIT = 1


def run_after_accept(settings: Settings) -> None:
    """Research the best waiting accepted card, then draft it. Never raises."""
    with agent_runs.hold("auto"):
        engine = create_db_engine(settings, ConnectionMode.SESSION)
        try:
            since = datetime.now(UTC) - timedelta(hours=24)
            with create_session_factory(engine)() as session:
                if is_paused(ControlsRepository(session).get(), datetime.now(UTC)):
                    log.info("paused, skipping auto pipeline")
                    return
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
