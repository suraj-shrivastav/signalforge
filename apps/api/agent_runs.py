"""Run pipeline stages on request, one at a time, in a background thread.

State lives in memory (single API process). The durable record of each stage is its
``stage_runs`` row; this only tells the agent whether a run is going and how the last ended.
"""

import logging
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import asdict, is_dataclass
from datetime import UTC, datetime
from typing import Any

from apps.worker import assess, cards, draft, research, tick
from signalforge.core.config import Settings
from signalforge.db.session import ConnectionMode, create_db_engine

log = logging.getLogger(__name__)

STAGES = ("tick", "assess", "cards", "research", "draft", "revise")
_LOCK = threading.Lock()
_STATE: dict[str, Any] = {"running": None, "last": {}}


def _run_stage(stage: str, settings: Settings, limit: int, retry_failed: bool) -> Any:
    if stage == "tick":
        return {"exit_code": tick.main([])}
    engine = create_db_engine(settings, ConnectionMode.SESSION)
    try:
        if stage == "assess":
            return assess.run(engine, limit)
        if stage == "cards":
            return cards.run(engine, limit)
        if stage == "research":
            return research.run(engine, limit, retry_failed=retry_failed)
        if stage == "draft":
            return draft.run(engine, limit, retry_failed=retry_failed)
        return draft.run(engine, limit, revise=True)
    finally:
        engine.dispose()


def _summary(result: Any) -> dict[str, Any]:
    if is_dataclass(result) and not isinstance(result, type):
        return {k: str(v) if k == "stage_run_id" else v for k, v in asdict(result).items()}
    return dict(result)


def start(stage: str, settings: Settings, limit: int, retry_failed: bool) -> bool:
    """Start ``stage`` in a thread. False when another run is still going."""
    return start_job(stage, lambda: _run_stage(stage, settings, limit, retry_failed))


def start_job(stage: str, job: Callable[[], Any]) -> bool:
    """Start any ``job`` under the one pipeline slot. False when another run is still going."""
    if not _LOCK.acquire(blocking=False):
        return False
    started = datetime.now(UTC).isoformat()
    _STATE["running"] = {"stage": stage, "started_at": started}

    def work() -> None:
        outcome: dict[str, Any]
        try:
            outcome = {"ok": True, "result": _summary(job())}
        except Exception as exc:
            log.exception("agent run failed", extra={"stage": stage})
            outcome = {"ok": False, "error": type(exc).__name__}
        try:
            # Record the result before the slot frees, so a poll never sees the previous run's.
            _STATE["last"][stage] = {
                "started_at": started,
                "finished_at": datetime.now(UTC).isoformat(),
                **outcome,
            }
        finally:
            _STATE["running"] = None
            _LOCK.release()

    threading.Thread(target=work, daemon=True).start()
    return True


@contextmanager
def hold(stage: str) -> Iterator[None]:
    """Wait for any run to finish, then hold the one pipeline slot until the block ends.

    For work started inside the API (the pass after an accept) so it never overlaps a run an
    agent started: both use this one lock, so research and drafting stay one at a time.
    """
    with _LOCK:
        _STATE["running"] = {"stage": stage, "started_at": datetime.now(UTC).isoformat()}
        try:
            yield
        finally:
            _STATE["running"] = None


def status() -> dict[str, Any]:
    return {"running": _STATE["running"], "last": dict(_STATE["last"])}


RunStarter = Callable[[str, Settings, int, bool], bool]
