from collections.abc import Iterable
from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from signalforge.core.artifacts.signal import RawSignal
from signalforge.core.errors import ProviderUnavailableError
from signalforge.db.models import Signal, StageRun, StageRunStatus
from signalforge.stages.ingest import run_ingest

pytestmark = pytest.mark.integration

SINCE = datetime(2026, 9, 23, tzinfo=UTC)


class FakeSource:
    name = "fake"
    source_type = "community"

    def __init__(
        self, signals: list[RawSignal] | None = None, error: Exception | None = None
    ) -> None:
        self._signals = signals or []
        self._error = error

    def fetch(self, since: datetime) -> Iterable[RawSignal]:  # noqa: ARG002
        if self._error:
            raise self._error
        return self._signals


def raw(n: int) -> RawSignal:
    return RawSignal(
        source="fake",
        source_type="community",
        canonical_url=f"https://example.com/ingest/{n}",
        title=f"T{n}",
        published_at=datetime(2026, 9, 24, tzinfo=UTC),
    )


def test_ingest_stores_signals_and_records_a_succeeded_run(db_session: Session) -> None:
    result = run_ingest(FakeSource([raw(1), raw(2)]), db_session, since=SINCE)

    assert (result.fetched, result.inserted) == (2, 2)
    run = db_session.get(StageRun, result.stage_run_id)
    assert run is not None
    assert run.status is StageRunStatus.SUCCEEDED
    assert run.stage == "ingest"
    assert run.finished_at is not None
    stored = db_session.scalars(select(Signal).where(Signal.source == "fake")).all()
    assert {s.produced_by for s in stored} == {result.stage_run_id}


def test_reingest_adds_no_duplicates(db_session: Session) -> None:
    source = FakeSource([raw(1)])
    assert run_ingest(source, db_session, since=SINCE).inserted == 1
    assert run_ingest(source, db_session, since=SINCE).inserted == 0


def test_failed_fetch_leaves_a_failed_run_with_the_reason_and_reraises(db_session: Session) -> None:
    with pytest.raises(ProviderUnavailableError):
        run_ingest(
            FakeSource(error=ProviderUnavailableError("upstream down")), db_session, since=SINCE
        )

    run = db_session.scalars(select(StageRun).where(StageRun.stage == "ingest")).one()
    assert run.status is StageRunStatus.FAILED
    assert run.error is not None
    assert "upstream down" in run.error
    assert run.finished_at is not None
