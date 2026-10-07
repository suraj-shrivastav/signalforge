import json
from collections.abc import Iterator
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import pytest
from apps.api.deps import get_article_repository
from apps.api.main import create_app
from apps.api.schemas import PublicArticleOut
from fastapi.testclient import TestClient

from signalforge.core.artifacts.article import (
    ArticleBody,
    ArticleClaim,
    ArticleCover,
    ArticleSection,
    ArticleSource,
)
from signalforge.core.artifacts.research import ClaimStatus
from signalforge.core.config import Settings

DSN = "postgresql://u:p@localhost:5432/db"
KEY = "editor-secret-value"
H = {"X-Editor-Key": KEY}
# Editor-only per the 2026-09-27 spec, plus internal spend and pipeline state.
EDITOR_ONLY = (
    "review_summary",
    "prompt_version",
    "model",
    "template",
    "cost_usd",
    "calls",
    "tokens",
    "evidence_span",
)

BODY = ArticleBody(
    title="Title",
    dek="Dek",
    sections=(ArticleSection(heading="H", paragraphs=("P",)),),
    claims=(
        ArticleClaim(
            text="c", evidence_span="span", document_indices=(0,), status=ClaimStatus.VERIFIED
        ),
    ),
    sources=(ArticleSource(label="example", url="https://example.com"),),
    cover=ArticleCover(alt="Alt"),
)


class StubRepo:
    def __init__(self) -> None:
        self.rows: dict[UUID, Any] = {}

    def add(self, draft: dict[str, Any]) -> UUID:
        card_id = uuid4()
        self.rows[card_id] = SimpleNamespace(
            card_id=card_id, status="drafted", template="explainer", draft=draft,
            review_summary="Single source. Claim 0", cost_usd=Decimal("0.12"), calls=2,
            tokens=900, created_at=datetime(2026, 10, 1, tzinfo=UTC),
        )  # fmt: skip
        return card_id

    def get(self, card_id: UUID) -> Any:
        return self.rows.get(card_id)

    def list_recent(self, limit: int) -> list[tuple[Any, str]]:
        self.limit = limit
        return [(row, "Signal title") for row in self.rows.values()]


@pytest.fixture
def ctx() -> Iterator[tuple[TestClient, StubRepo]]:
    app = create_app(Settings(_env_file=None, database_url=DSN, editor_api_key=KEY))  # type: ignore[call-arg,arg-type]
    repo = StubRepo()
    app.dependency_overrides[get_article_repository] = lambda: repo
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client, repo


def test_editor_draft_requires_key(ctx: tuple[TestClient, StubRepo]) -> None:
    client, repo = ctx
    card_id = repo.add(BODY.model_dump(mode="json"))
    assert client.get(f"/editor/drafts/{card_id}").status_code == 401
    assert client.get(f"/editor/drafts/{card_id}", headers={"X-Editor-Key": "x"}).status_code == 401


def test_editor_draft_returns_every_field(ctx: tuple[TestClient, StubRepo]) -> None:
    client, repo = ctx
    card_id = repo.add(BODY.model_dump(mode="json"))
    r = client.get(f"/editor/drafts/{card_id}", headers=H)
    assert r.status_code == 200
    body = r.json()
    assert (body["template"], body["review_summary"], body["calls"]) == (
        "explainer",
        "Single source. Claim 0",
        2,
    )
    assert body["draft"]["claims"][0]["status"] == "verified"
    assert body["draft"]["sources"] == [{"label": "example", "url": "https://example.com"}]


def test_failed_draft_has_null_body(ctx: tuple[TestClient, StubRepo]) -> None:
    client, repo = ctx
    card_id = repo.add({})
    assert client.get(f"/editor/drafts/{card_id}", headers=H).json()["draft"] is None


def test_missing_draft_is_404(ctx: tuple[TestClient, StubRepo]) -> None:
    assert ctx[0].get(f"/editor/drafts/{uuid4()}", headers=H).status_code == 404


def test_draft_list_requires_key(ctx: tuple[TestClient, StubRepo]) -> None:
    assert ctx[0].get("/editor/drafts").status_code == 401


def test_draft_list_summarises_each_draft(ctx: tuple[TestClient, StubRepo]) -> None:
    client, repo = ctx
    repo.add(BODY.model_dump(mode="json"))
    repo.add({})
    r = client.get("/editor/drafts?limit=5", headers=H)
    assert r.status_code == 200
    assert repo.limit == 5
    full, empty = r.json()
    assert (full["title"], full["signal_title"], full["claim_counts"]) == (
        "Title",
        "Signal title",
        {"verified": 1},
    )
    assert (empty["title"], empty["claim_counts"]) == ("", {})
    assert "review_summary" not in full


@pytest.mark.parametrize("q", ["limit=0", "limit=101"])
def test_draft_list_limit_validated(ctx: tuple[TestClient, StubRepo], q: str) -> None:
    assert ctx[0].get(f"/editor/drafts?{q}", headers=H).status_code == 422


def _keys(value: object) -> set[str]:
    if isinstance(value, dict):
        return set(value) | {k for v in value.values() for k in _keys(v)}
    if isinstance(value, list):
        return {k for v in value for k in _keys(v)}
    return set()


def test_public_shape_omits_editor_only_fields() -> None:
    dumped = PublicArticleOut.from_body(BODY).model_dump(mode="json")
    leaked = _keys(dumped) & set(EDITOR_ONLY)
    assert leaked == set()
    schema = json.dumps(PublicArticleOut.model_json_schema())
    assert not [name for name in EDITOR_ONLY if f'"{name}"' in schema]
    assert dumped["claims"] == [{"text": "c", "status": "verified", "source_indices": [0]}]
