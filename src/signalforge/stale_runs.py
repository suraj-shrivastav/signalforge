"""Stage runs are daemon threads: a restart kills them and leaves 'running' rows behind.

Mark those rows failed so the state machine retries them instead of waiting forever.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import update
from sqlalchemy.orm import Session

from signalforge.db.models.article import ArticleDraftRow
from signalforge.db.models.ops import StageRun, StageRunStatus
from signalforge.db.models.research import ResearchPackageRow

INTERRUPTED = "interrupted"


@dataclass(frozen=True)
class SweepResult:
    stage_runs: int
    research: int
    drafts: int


def sweep_stale_runs(
    session: Session, now: datetime, older_than: timedelta = timedelta(minutes=90)
) -> SweepResult:
    """Fail rows still in flight past ``older_than``; ``updated_at`` is bumped by onupdate."""
    cutoff = now - older_than
    runs = session.execute(
        update(StageRun)
        .where(StageRun.status == StageRunStatus.RUNNING, StageRun.started_at < cutoff)
        .values(
            status=StageRunStatus.FAILED,
            finished_at=now,
            error=f"{INTERRUPTED}: process restarted",
        )
    ).rowcount  # type: ignore[attr-defined]
    research = session.execute(
        update(ResearchPackageRow)
        .where(ResearchPackageRow.status == "researching", ResearchPackageRow.updated_at < cutoff)
        .values(status="failed", failure_reason=INTERRUPTED)
    ).rowcount  # type: ignore[attr-defined]
    drafts = session.execute(
        update(ArticleDraftRow)
        .where(ArticleDraftRow.status == "drafting", ArticleDraftRow.updated_at < cutoff)
        .values(status="failed", failure_reason=INTERRUPTED)
    ).rowcount  # type: ignore[attr-defined]
    session.commit()
    return SweepResult(runs or 0, research or 0, drafts or 0)
