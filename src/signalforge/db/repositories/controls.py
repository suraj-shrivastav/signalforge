"""The pipeline control row: kill switch and 6-hour slot lease. Every call locks the row."""

from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from signalforge.db.models.ops import PipelineControl

SINGLETON_ID = 1


@dataclass(frozen=True)
class SlotClaim:
    claimed: bool
    slot: str
    failures: int


class ControlsRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self) -> PipelineControl:
        row = self._session.get(PipelineControl, SINGLETON_ID, with_for_update=True)
        if row is None:  # migration 0013 seeds it; a missing row is a broken database
            raise LookupError("pipeline_controls row 1 is missing; run alembic upgrade head")
        return row

    def pause(
        self, reason: str, actor: str, now: datetime, until: datetime | None = None
    ) -> PipelineControl:
        row = self.get()
        row.paused, row.paused_reason, row.paused_by = True, reason, actor
        row.paused_at, row.paused_until = now, until
        self._session.flush()
        return row

    def resume(self, actor: str) -> PipelineControl:
        row = self.get()
        row.paused, row.paused_reason, row.paused_until = False, None, None
        row.paused_by = actor
        self._session.flush()
        return row

    def claim_slot(
        self,
        slot: str,
        now: datetime,
        lease: timedelta,
        max_failures: int = 3,
        holder: str | None = None,
    ) -> SlotClaim:
        """Take the lease. The same ``holder`` asking again gets its own claim back unchanged."""
        row = self.get()
        same = row.slot == slot
        failures = row.slot_failures if same else 0
        leased = row.slot_status == "running" and (
            row.slot_lease_until is not None and row.slot_lease_until > now
        )
        if leased and same and holder is not None and holder == row.slot_holder:
            return SlotClaim(True, slot, row.slot_failures)  # a retry after a lost reply
        if leased or (same and row.slot_status == "done") or failures >= max_failures:
            return SlotClaim(False, slot, failures)
        row.slot, row.slot_status, row.slot_failures = slot, "running", failures
        row.slot_lease_until = now + lease
        row.slot_holder = holder
        self._session.flush()
        return SlotClaim(True, slot, failures)

    def release_slot(self, slot: str) -> PipelineControl:
        """End a running slot that was paused, not failed: shown as failed, failures unchanged."""
        row = self.get()
        if row.slot == slot and row.slot_status == "running":
            row.slot_status = "failed"
            row.slot_lease_until = None
            row.slot_holder = None
            self._session.flush()
        return row

    def finish_slot(self, slot: str, ok: bool) -> PipelineControl:
        row = self.get()
        if row.slot == slot:
            row.slot_status = "done" if ok else "failed"
            row.slot_failures += 0 if ok else 1
            row.slot_lease_until = None
            row.slot_holder = None
            self._session.flush()
        return row
