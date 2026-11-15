# ruff: noqa: ARG002, PT018
from collections.abc import Iterator
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest
from apps.api.deps import get_controls_repository
from apps.api.main import create_app
from fastapi.testclient import TestClient

from signalforge.core.config import Settings
from signalforge.db.repositories.controls import SlotClaim

DSN = "postgresql://u:p@localhost:5432/db"
KEY = "editor-secret-value"
H = {"X-Editor-Key": KEY}


class StubControls:
    def __init__(self) -> None:
        self.row = SimpleNamespace(
            paused=False, paused_reason=None, paused_by=None, paused_until=None,
            slot=None, slot_status=None, slot_failures=0,
        )  # fmt: skip
        self.claims: list[str] = []

    def get(self) -> Any:
        return self.row

    def pause(self, reason: str, actor: str, now: datetime, until: datetime | None = None) -> Any:
        self.row.paused, self.row.paused_reason, self.row.paused_by = True, reason, actor
        self.row.paused_until = until
        return self.row

    def resume(self, actor: str) -> Any:
        self.row.paused, self.row.paused_reason, self.row.paused_until = False, None, None
        return self.row

    def claim_slot(self, slot: str, now: datetime, lease: Any, max_failures: int = 3) -> SlotClaim:
        self.claims.append(slot)
        return SlotClaim(len(self.claims) == 1, slot, 0)

    def finish_slot(self, slot: str, ok: bool) -> Any:
        self.row.slot_status = "done" if ok else "failed"
        return self.row


@pytest.fixture
def ctx() -> Iterator[tuple[TestClient, StubControls]]:
    app = create_app(Settings(_env_file=None, database_url=DSN, editor_api_key=KEY))  # type: ignore[call-arg,arg-type]
    stub = StubControls()
    app.dependency_overrides[get_controls_repository] = lambda: stub
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client, stub


def test_pause_records_actor_and_resume_clears(ctx: tuple[TestClient, StubControls]) -> None:
    client, stub = ctx
    r = client.post("/agent/controls/pause", json={"reason": "drill"}, headers=H)
    assert r.status_code == 200 and r.json()["paused"] is True
    assert stub.row.paused_by == "editor" and stub.row.paused_until is None
    assert client.post("/agent/controls/resume", headers=H).json()["paused"] is False


def test_breaker_pause_sets_expiry(ctx: tuple[TestClient, StubControls]) -> None:
    client, stub = ctx
    client.post("/agent/controls/pause", json={"reason": "canary", "minutes": 360}, headers=H)
    assert stub.row.paused_until is not None and stub.row.paused_until > datetime.now(UTC)


def test_paused_blocks_stage_runs_and_publish(ctx: tuple[TestClient, StubControls]) -> None:
    client, stub = ctx
    stub.row.paused = True
    assert client.post("/agent/run/tick", headers=H).status_code == 423
    assert client.post("/agent/publish-next", headers=H).status_code == 423


def test_slot_claim_is_exclusive(ctx: tuple[TestClient, StubControls]) -> None:
    client, _ = ctx
    body = {"slot": "2026-11-15-06"}
    assert client.post("/agent/controls/slot/claim", json=body, headers=H).json()["claimed"]
    assert not client.post("/agent/controls/slot/claim", json=body, headers=H).json()["claimed"]


def test_controls_need_a_key(ctx: tuple[TestClient, StubControls]) -> None:
    client, _ = ctx
    assert client.get("/agent/controls").status_code in (401, 403)
