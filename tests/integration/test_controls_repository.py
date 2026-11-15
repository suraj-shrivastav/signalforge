from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from signalforge.db.repositories.controls import ControlsRepository

NOW = datetime(2026, 11, 15, 6, 5, tzinfo=UTC)
LEASE = timedelta(hours=2)


def test_pause_and_resume_record_the_actor(db_session: Session) -> None:
    repo = ControlsRepository(db_session)
    row = repo.pause("canary failed", "agent", NOW, until=NOW + timedelta(hours=6))
    assert (row.paused, row.paused_by, row.paused_reason) == (True, "agent", "canary failed")
    row = repo.resume("editor")
    assert (row.paused, row.paused_until, row.paused_reason) == (False, None, None)


def test_claim_slot_once_until_finished(db_session: Session) -> None:
    repo = ControlsRepository(db_session)
    assert repo.claim_slot("2026-11-15-06", NOW, LEASE).claimed
    # A second run while the lease holds does not claim.
    assert not repo.claim_slot("2026-11-15-06", NOW + timedelta(minutes=15), LEASE).claimed
    repo.finish_slot("2026-11-15-06", ok=True)
    # A finished slot is not re-run.
    assert not repo.claim_slot("2026-11-15-06", NOW + timedelta(minutes=30), LEASE).claimed


def test_failed_slot_retries_until_max_failures(db_session: Session) -> None:
    repo = ControlsRepository(db_session)
    for attempt in range(3):
        claim = repo.claim_slot("2026-11-15-12", NOW, LEASE)
        assert claim.claimed
        assert claim.failures == attempt
        repo.finish_slot("2026-11-15-12", ok=False)
    assert not repo.claim_slot("2026-11-15-12", NOW, LEASE).claimed


def test_expired_lease_can_be_reclaimed(db_session: Session) -> None:
    repo = ControlsRepository(db_session)
    assert repo.claim_slot("2026-11-15-18", NOW, LEASE).claimed
    assert repo.claim_slot("2026-11-15-18", NOW + LEASE + timedelta(seconds=1), LEASE).claimed


def test_new_slot_resets_failures(db_session: Session) -> None:
    repo = ControlsRepository(db_session)
    repo.claim_slot("2026-11-15-00", NOW, LEASE)
    repo.finish_slot("2026-11-15-00", ok=False)
    assert repo.claim_slot("2026-11-15-06", NOW, LEASE).failures == 0
