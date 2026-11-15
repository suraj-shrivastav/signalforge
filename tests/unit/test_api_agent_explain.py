from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import pytest
from apps.api.deps import get_controls_repository, get_pipeline_repository, get_published_repository
from apps.api.main import create_app
from fastapi.testclient import TestClient

from signalforge.core.config import Settings
from signalforge.db.repositories.pipeline import PipelineRepository
from signalforge.explain import CardFacts

DSN = "postgresql://u:p@localhost:5432/db"
KEY = "editor-secret-value"
H = {"X-Editor-Key": KEY}
NOW = datetime.now(UTC)


class StubPipeline:
    state_of = staticmethod(PipelineRepository.state_of)

    def __init__(self, cards: list[CardFacts]) -> None:
        self.cards = cards

    def facts(
        self, limit: int, *, accepted_only: bool = True, card_id: UUID | None = None
    ) -> list[CardFacts]:
        out = [c for c in self.cards if not accepted_only or c.decision == "accepted"]
        if card_id is not None:
            out = [c for c in out if c.card_id == card_id]
        return sorted(out, key=lambda c: c.created_at, reverse=True)[:limit]


class StubControls:
    def __init__(self) -> None:
        self.row = SimpleNamespace(paused=False, paused_reason=None, paused_until=None)

    def get(self) -> Any:
        return self.row


class StubPublished:
    def __init__(self) -> None:
        self.times: list[datetime] = []

    def published_times_since(self, since: datetime) -> list[datetime]:  # noqa: ARG002
        return self.times

    def get_by_slug(self, slug: str) -> Any:  # noqa: ARG002
        return None


def card(title: str = "A card", age: int = 0, **kw: Any) -> CardFacts:
    kw.setdefault("decision", "accepted")
    return CardFacts(card_id=uuid4(), title=title, created_at=NOW - timedelta(hours=age), **kw)


def approved(title: str, age: int) -> CardFacts:
    return card(
        title, age, research_status="researched", draft_status="drafted", review_status="approved"
    )


Ctx = tuple[TestClient, StubControls, StubPublished, list[CardFacts]]


@pytest.fixture
def ctx() -> Iterator[Ctx]:
    app = create_app(
        Settings(  # type: ignore[call-arg]
            _env_file=None,
            database_url=DSN,  # type: ignore[arg-type]
            editor_api_key=KEY,  # type: ignore[arg-type]
            site_url="https://site.test/",
        )
    )
    cards: list[CardFacts] = []
    controls, published = StubControls(), StubPublished()
    app.dependency_overrides[get_pipeline_repository] = lambda: StubPipeline(cards)
    app.dependency_overrides[get_controls_repository] = lambda: controls
    app.dependency_overrides[get_published_repository] = lambda: published
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client, controls, published, cards


def explain(client: TestClient, c: CardFacts) -> dict[str, Any]:
    r = client.get(f"/agent/cards/{c.card_id}/explain", headers=H)
    assert r.status_code == 200
    return r.json()  # type: ignore[no-any-return]


def test_requires_key(ctx: Ctx) -> None:
    client, *_ = ctx
    assert client.get(f"/agent/cards/{uuid4()}/explain").status_code in (401, 403)
    assert client.get("/agent/publish-queue").status_code in (401, 403)


def test_unknown_card_is_404(ctx: Ctx) -> None:
    client, *_ = ctx
    assert client.get(f"/agent/cards/{uuid4()}/explain", headers=H).status_code == 404


def test_waiting_for_pace_shows_slot_and_position(ctx: Ctx) -> None:
    client, _, published, cards = ctx
    published.times = [NOW - timedelta(hours=1)]
    first, second = approved("First", 5), approved("Second", 2)
    cards += [second, first]
    body = explain(client, second)
    assert body["next_action"] == "publish"
    assert body["queue_position"] == 2
    assert body["summary"].startswith("Waiting for the publish pace: next slot ")
    assert body["summary"].endswith("2nd in queue")
    assert explain(client, first)["queue_position"] == 1


def test_closed_research(ctx: Ctx) -> None:
    client, _, _, cards = ctx
    c = card(
        research_status="needs_more_info", research_attempts=2, research_failure="thin: 1 claim"
    )
    cards.append(c)
    body = explain(client, c)
    assert body["summary"] == "Closed: research came back thin twice (thin)"
    assert body["research"]["failure_reason"] == "thin: 1 claim"


def test_closed_draft(ctx: Ctx) -> None:
    client, _, _, cards = ctx
    c = card(
        research_status="researched", draft_status="failed", draft_attempts=2,
        draft_failure="error: boom",
    )  # fmt: skip
    cards.append(c)
    assert explain(client, c)["summary"] == "Closed: the draft failed twice (error)"


def test_revise_exhausted_with_last_reasons(ctx: Ctx) -> None:
    client, _, _, cards = ctx
    log = [
        {"type": "redraft"},
        {"type": "redraft_failed"},
        {"type": "review", "reasons": ["a", "b", "c", "too short"]},
    ]
    c = card(
        research_status="researched", draft_status="drafted", review_status="revise",
        review_log=log,
    )  # fmt: skip
    cards.append(c)
    body = explain(client, c)
    assert body["stage"] == "revise_exhausted"
    assert body["summary"].startswith("Closed: the draft still failed review after 2 of 2")
    assert body["summary"].endswith("too short")
    assert body["review"]["last_reasons"] == ["b", "c", "too short"]
    assert body["review"]["redrafts_used"] == 2


def test_unpublished(ctx: Ctx) -> None:
    client, _, _, cards = ctx
    c = card(
        research_status="researched", draft_status="drafted", review_status="approved",
        published_status="unpublished", slug="gone",
    )  # fmt: skip
    cards.append(c)
    body = explain(client, c)
    assert body["summary"] == "Unpublished by the owner"
    assert body["published"]["url"] is None


def test_paused_wins_over_waiting(ctx: Ctx) -> None:
    client, controls, _, cards = ctx
    controls.row.paused, controls.row.paused_reason = True, "provider outage"
    c = approved("Held", 1)
    cards.append(c)
    body = explain(client, c)
    assert body["summary"].startswith("Paused: provider outage")
    assert body["paused"] is True


def test_published_has_url(ctx: Ctx) -> None:
    client, _, _, cards = ctx
    c = card(
        research_status="researched", draft_status="drafted", review_status="approved",
        published_status="published", slug="my-post", has_cover=True, has_figure=True,
    )  # fmt: skip
    cards.append(c)
    body = explain(client, c)
    assert body["summary"] == "Published"
    assert body["published"]["url"] == "https://site.test/articles/my-post"


def test_search_returns_best_five_matches(ctx: Ctx) -> None:
    client, _, _, cards = ctx
    cards += [card(f"Quantum chips {i}", i) for i in range(7)] + [card("Other news", 9)]
    r = client.get("/agent/cards/explain", params={"q": "quantum chips"}, headers=H)
    assert r.status_code == 200
    titles = [m["title"] for m in r.json()["matches"]]
    assert len(titles) == 5
    assert all("Quantum" in t for t in titles)


def test_search_by_slug(ctx: Ctx) -> None:
    client, _, _, cards = ctx
    cards.append(
        card(
            "Some title",
            research_status="researched",
            draft_status="drafted",
            review_status="approved",
            published_status="published",
            slug="the-slug",
        )
    )
    r = client.get("/agent/cards/explain", params={"q": "the-slug"}, headers=H)
    assert [m["title"] for m in r.json()["matches"]] == ["Some title"]


def test_publish_queue_oldest_first_with_pace(ctx: Ctx) -> None:
    client, controls, published, cards = ctx
    published.times = [NOW - timedelta(hours=1)]
    newer, older = approved("Newer", 1), approved("Older", 6)
    cards += [newer, older]
    controls.row.paused, controls.row.paused_reason = True, "drill"
    body = client.get("/agent/publish-queue", headers=H).json()
    assert [i["title"] for i in body["items"]] == ["Older", "Newer"]
    assert [i["position"] for i in body["items"]] == [1, 2]
    first = datetime.fromisoformat(body["items"][0]["estimated_publish_at"])
    second = datetime.fromisoformat(body["items"][1]["estimated_publish_at"])
    assert second - first == timedelta(minutes=body["min_gap_minutes"])
    assert body["paused"] is True
    assert body["paused_reason"] == "drill"
    assert body["waiting"] == 2
