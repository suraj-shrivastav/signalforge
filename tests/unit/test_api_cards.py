import logging
from collections.abc import Iterator
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import pytest
from apps.api.deps import get_card_repository
from apps.api.main import create_app
from fastapi.testclient import TestClient

from signalforge.core.config import Settings
from signalforge.db.repositories.cards import QueueItem

DSN = "postgresql://u:p@localhost:5432/db"
KEY = "editor-secret-value"
NOW = datetime(2026, 9, 27, tzinfo=UTC)


def _item() -> QueueItem:
    card = SimpleNamespace(
        id=uuid4(), schema_version=1, signal_id=uuid4(), what_happened="w", why_it_matters="y",
        novelty=0.5, signal_strength=0.5, coverage_gap="g", suggested_angle="a", format="article",
        evergreen_score=0.1, confidence=0.9, risk_flags=[], prompt_version="v1", model="m",
        score=0.7, created_at=NOW, llm_call_id=uuid4(), stage_run_id=uuid4(),
    )  # fmt: skip
    return QueueItem(
        card=card,  # type: ignore[arg-type]
        signal_title="t",
        source="hn",
        canonical_url="u",
        wildcard=False,
        status="proposed",
    )


class StubRepo:
    def __init__(self) -> None:
        self.known = {uuid4()}
        self.added: list[tuple[Any, ...]] = []
        self.queue_kwargs: dict[str, Any] = {}

    def queue(self, **kwargs: Any) -> list[QueueItem]:
        self.queue_kwargs = kwargs
        return [_item()]

    def exists(self, card_id: UUID) -> bool:
        return card_id in self.known

    def add_decision(self, card_id: UUID, *args: Any) -> Any:
        self.added.append((card_id, *args))
        return SimpleNamespace(
            id=uuid4(), topic_card_id=card_id, decision=args[0], reason_tags=list(args[1]),
            note=args[2], decision_ms=args[3], decided_at=NOW,
        )  # fmt: skip


def make(key: str | None = KEY) -> tuple[TestClient, StubRepo]:
    kwargs: dict[str, Any] = {} if key is None else {"editor_api_key": key}
    app = create_app(Settings(_env_file=None, database_url=DSN, **kwargs))  # type: ignore[call-arg,arg-type]
    repo = StubRepo()
    app.dependency_overrides[get_card_repository] = lambda: repo
    return TestClient(app, raise_server_exceptions=False), repo


@pytest.fixture
def ctx() -> Iterator[tuple[TestClient, StubRepo]]:
    client, repo = make()
    with client:
        yield client, repo


H = {"X-Editor-Key": KEY}
BODY = {"decision": "accepted", "reason_tags": ["timely"], "note": "n", "decision_ms": 1200}


def url(repo: StubRepo) -> str:
    return f"/cards/{next(iter(repo.known))}/decision"


def test_queue_open_read_and_no_internal_fields(ctx: tuple[TestClient, StubRepo]) -> None:
    client, repo = ctx
    r = client.get("/cards/queue?limit=3&days=2")
    assert r.status_code == 200
    assert repo.queue_kwargs["limit"] == 3
    item = r.json()[0]
    assert item["signal"]["title"] == "t"
    assert "llm_call_id" not in item
    assert "stage_run_id" not in item


@pytest.mark.parametrize("q", ["limit=0", "limit=51", "days=0", "days=31"])
def test_queue_params_validated(ctx: tuple[TestClient, StubRepo], q: str) -> None:
    assert ctx[0].get(f"/cards/queue?{q}").status_code == 422


def test_401_body_identical_for_missing_and_wrong(ctx: tuple[TestClient, StubRepo]) -> None:
    client, repo = ctx
    a = client.post(url(repo), json=BODY)
    b = client.post(url(repo), json=BODY, headers={"X-Editor-Key": "wrong"})
    assert a.status_code == b.status_code == 401
    assert a.json()["error"]["code"] == b.json()["error"]["code"]
    assert a.json()["error"]["message"] == b.json()["error"]["message"]
    assert repo.added == []


def test_unset_key_is_503_even_with_a_header() -> None:
    client, repo = make(key=None)
    with client:
        r = client.post(url(repo), json=BODY, headers={"X-Editor-Key": "anything"})
    assert r.status_code == 503
    assert r.json()["error"]["code"] == "editor_key_not_configured"
    assert repo.added == []


def test_valid_write_is_201(ctx: tuple[TestClient, StubRepo]) -> None:
    client, repo = ctx
    r = client.post(url(repo), json=BODY, headers=H)
    assert r.status_code == 201
    out = r.json()
    assert set(out) == {
        "id",
        "card_id",
        "decision",
        "reason_tags",
        "note",
        "decision_ms",
        "decided_at",
    }
    assert out["reason_tags"] == ["timely"]
    assert len(repo.added) == 1


@pytest.mark.parametrize(
    "patch",
    [
        {"decision": "maybe"},
        {"reason_tags": ["nope"]},
        {"reason_tags": ["timely", "timely"]},
        {"reason_tags": ["timely"] * 9},
        {"note": "x" * 501},
        {"decision_ms": -1},
        {"decision_ms": 3_600_001},
    ],
)
def test_invalid_bodies_are_422(ctx: tuple[TestClient, StubRepo], patch: dict[str, Any]) -> None:
    client, repo = ctx
    assert client.post(url(repo), json={**BODY, **patch}, headers=H).status_code == 422
    assert repo.added == []


def test_null_decision_ms_ok_unknown_card_404_bad_uuid_422(
    ctx: tuple[TestClient, StubRepo],
) -> None:
    client, repo = ctx
    assert client.post(url(repo), json={**BODY, "decision_ms": None}, headers=H).status_code == 201
    assert client.post(f"/cards/{uuid4()}/decision", json=BODY, headers=H).status_code == 404
    assert client.post("/cards/not-a-uuid/decision", json=BODY, headers=H).status_code == 422


def test_key_never_in_logs_or_bodies(
    ctx: tuple[TestClient, StubRepo],
    caplog: pytest.LogCaptureFixture,
    capsys: pytest.CaptureFixture[str],
) -> None:
    client, repo = ctx
    with caplog.at_level(logging.DEBUG):
        rs = [
            client.post(url(repo), json=BODY, headers=H),
            client.post(url(repo), json=BODY, headers={"X-Editor-Key": KEY + "x"}),
            client.post(url(repo), json={**BODY, "decision": "bad"}, headers=H),
        ]
    assert KEY not in caplog.text
    assert KEY not in capsys.readouterr().err
    assert all(KEY not in r.text for r in rs)


def test_unauthenticated_precedes_404_and_body_validation(
    ctx: tuple[TestClient, StubRepo],
) -> None:
    client, repo = ctx
    assert client.post(f"/cards/{uuid4()}/decision", json=BODY).status_code == 401
    assert client.post(url(repo), json={"decision": "bad"}).status_code == 401
    assert client.post(url(repo), content=b"{not json").status_code == 401
    assert client.post("/cards/not-a-uuid/decision", json=BODY).status_code == 401
    r = client.post(url(repo), content=b"{not json", headers=H)
    assert r.status_code == 422


def test_non_ascii_key_is_401(ctx: tuple[TestClient, StubRepo]) -> None:
    client, repo = ctx
    r = client.post(url(repo), json=BODY, headers={"X-Editor-Key": "café".encode()})
    assert r.status_code == 401


def test_empty_configured_key_is_503() -> None:
    client, repo = make(key="")
    with client:
        assert client.post(url(repo), json=BODY, headers={"X-Editor-Key": ""}).status_code == 503


def test_401_body_identical_minus_correlation_id(ctx: tuple[TestClient, StubRepo]) -> None:
    client, repo = ctx

    def body(headers: dict[str, str]) -> dict[str, Any]:
        err = client.post(url(repo), json=BODY, headers=headers).json()["error"]
        err.pop("correlation_id")
        return dict(err)

    assert body({}) == body({"X-Editor-Key": "wrong"})


def test_integrity_error_on_insert_is_404(ctx: tuple[TestClient, StubRepo]) -> None:
    from sqlalchemy.exc import IntegrityError

    client, repo = ctx

    def boom(*_: Any) -> Any:
        raise IntegrityError("s", {}, Exception("fk"))

    repo.add_decision = boom  # type: ignore[method-assign,assignment]
    r = client.post(url(repo), json=BODY, headers=H)
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "not_found"


def test_503_logs_warning_without_key(capsys: pytest.CaptureFixture[str]) -> None:
    # configure_logging writes JSON to stderr and stops propagation, so caplog sees nothing.
    client, repo = make(key=None)
    with client:
        client.post(url(repo), json=BODY, headers=H)
    logged = capsys.readouterr().err
    assert "editor key not configured" in logged
    assert KEY not in logged


@pytest.mark.parametrize(("limit", "wild"), [(1, 0), (2, 1), (3, 1), (15, 2)])
def test_queue_uses_real_select_queue(limit: int, wild: int) -> None:
    from apps.api.deps import get_card_repository as dep

    from signalforge.db.repositories.cards import CardRepository

    items = []
    for i in range(20):
        it = _item()
        it.card.score = 1 - i / 100
        it.card.novelty = i / 100
        items.append(it)

    class Real(CardRepository):
        def __init__(self) -> None:
            pass

        def queue(self, *, limit: int = 15, wildcard_slots: int = 2, since: datetime) -> Any:  # noqa: ARG002
            from signalforge.db.repositories.cards import select_queue

            return select_queue(items, limit, wildcard_slots)

    client, _ = make()
    client.app.dependency_overrides[dep] = lambda: Real()  # type: ignore[attr-defined]
    with client:
        r = client.get(f"/cards/queue?limit={limit}")
    assert r.status_code == 200
    out = r.json()
    assert len(out) == limit
    assert sum(c["wildcard"] for c in out) == wild


def test_commit_failure_is_500_not_201() -> None:
    from apps.api.deps import get_card_repository as dep

    from signalforge.db.repositories.cards import CardRepository
    from signalforge.db.session import session_scope

    class Sess:
        def commit(self) -> None:
            raise RuntimeError("commit failed")

        def rollback(self) -> None: ...
        def close(self) -> None: ...

    stub = StubRepo()

    def factory() -> Any:
        return Sess()

    def real_dep() -> Any:
        with session_scope(factory) as _:  # type: ignore[arg-type]
            yield stub

    client, _ = make()
    client.app.dependency_overrides.pop(dep, None)  # type: ignore[attr-defined]
    client.app.dependency_overrides[dep] = real_dep  # type: ignore[attr-defined]
    _ = CardRepository
    with client:
        r = client.post(url(stub), json=BODY, headers=H)
    assert r.status_code == 500
