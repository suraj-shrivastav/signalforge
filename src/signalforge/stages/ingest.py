"""Ingest: fetch signals from a source and store the new ones.

A plain function so it can be called from a CLI, an HTTP trigger or, later, a
queue job without change. It records what it did in ``stage_runs`` (PRD §30).
"""

import hashlib
import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from signalforge.core.logging import correlation_id
from signalforge.core.protocols import Source
from signalforge.db.models import StageRun, StageRunStatus
from signalforge.db.repositories.signals import SignalRepository

log = logging.getLogger(__name__)

INGEST_STAGE = "ingest"
_ENTITY_NAMESPACE = uuid.UUID("6f1c2f0e-3f0a-4b8e-9d55-0c6a6a1d7a01")
_MAX_ERROR_CHARS = 2000


@dataclass(frozen=True)
class IngestResult:
    source: str
    fetched: int
    inserted: int
    stage_run_id: uuid.UUID


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def run_ingest(source: Source, session: Session, *, since: datetime) -> IngestResult:
    """Fetch from ``source`` since ``since``, store unseen signals, record the run.

    Failures leave a ``failed`` stage run with the reason and are re-raised.
    """
    started_at = datetime.now(UTC)
    run = StageRun(
        stage=INGEST_STAGE,
        entity_id=uuid.uuid5(_ENTITY_NAMESPACE, source.name),
        # ponytail: the start time makes every run unique, so the idempotency cache
        # never short-circuits a re-fetch. Real input/config hashing arrives with the
        # generic stage runner.
        input_hash=_sha(f"{source.name}|{since.isoformat()}|{started_at.isoformat()}"),
        stage_config_hash=_sha(source.name),
        status=StageRunStatus.RUNNING,
    )
    session.add(run)
    # Commit before doing any work: the run row must survive a rollback of the work.
    session.commit()
    run_id = run.id

    with correlation_id(str(run_id)):
        try:
            signals = list(source.fetch(since))
            stamped = [signal.derive(produced_by=run_id) for signal in signals]
            inserted = SignalRepository(session).insert_new(stamped)
            run.status = StageRunStatus.SUCCEEDED
            run.finished_at = datetime.now(UTC)
            run.output_schema_version = stamped[0].schema_version if stamped else None
            session.commit()
        except Exception as exc:
            session.rollback()
            failed = session.get(StageRun, run_id)
            if failed is not None:
                failed.status = StageRunStatus.FAILED
                failed.error = str(exc)[:_MAX_ERROR_CHARS]
                failed.finished_at = datetime.now(UTC)
                session.commit()
            log.exception("ingest failed", extra={"source": source.name})
            raise
        log.info(
            "ingest finished",
            extra={"source": source.name, "fetched": len(signals), "inserted": inserted},
        )
    return IngestResult(
        source=source.name, fetched=len(signals), inserted=inserted, stage_run_id=run_id
    )
