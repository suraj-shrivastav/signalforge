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
    ArticleFlag,
    ArticleSection,
    ArticleSource,
    FlagKind,
)
from signalforge.core.artifacts.research import ClaimStatus
from signalforge.core.config import Settings

DSN = "postgresql://u:p@localhost:5432/db"
KEY = "editor-secret-value"
H = {"X-Editor-Key": KEY}
# Editor-only per the 2026-09-27 spec, plus internal spend and pipeline state.
EDITOR_ONLY = (
    "review_summary",
    "failure_reason",
    "review_status",
    "review_note",
    "reviewed_at",
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
            tokens=900, review_status="pending", review_note="", reviewed_at=None,
            failure_reason=None if draft else "ProviderRejectedError: status=402",
            created_at=datetime(2026, 10, 1, tzinfo=UTC),
        )  # fmt: skip
        return card_id

    def get(self, card_id: UUID) -> Any:
        return self.rows.get(card_id)

    def save_edit(self, row: Any, body: ArticleBody, event: dict[str, Any]) -> None:
        row.draft = body.model_dump(mode="json")
        row.log = [*getattr(row, "log", []), event]

    def save_review(self, row: Any, decision: str, note: str, event: dict[str, Any]) -> None:
        row.review_status, row.review_note = decision, note
        row.log = [*getattr(row, "log", []), event]

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
    body = client.get(f"/editor/drafts/{card_id}", headers=H).json()
    assert body["draft"] is None
    assert body["failure_reason"] == "ProviderRejectedError: status=402"


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


FLAGGED = BODY.model_copy(
    update={
        "sections": (ArticleSection(heading="H", paragraphs=("Good one. Bad one.",)),),
        "flags": (ArticleFlag(section=0, paragraph=0, text="Bad one.", kind=FlagKind.UNCITED),),
    }
)


def test_editing_a_flagged_sentence_clears_its_flag_and_logs_it(
    ctx: tuple[TestClient, StubRepo],
) -> None:
    client, repo = ctx
    card_id = repo.add(FLAGGED.model_dump(mode="json"))
    r = client.post(
        f"/editor/drafts/{card_id}/sentence",
        headers=H,
        json={"section": 0, "paragraph": 0, "text": "Bad one.", "replacement": "Fixed one."},
    )
    assert r.status_code == 200
    body = r.json()["draft"]
    assert body["sections"][0]["paragraphs"] == ["Good one. Fixed one."]
    assert body["flags"] == []
    assert repo.rows[card_id].log[0]["before"] == "Bad one."


def test_edit_of_a_missing_sentence_is_422(ctx: tuple[TestClient, StubRepo]) -> None:
    client, repo = ctx
    card_id = repo.add(FLAGGED.model_dump(mode="json"))
    r = client.post(
        f"/editor/drafts/{card_id}/sentence",
        headers=H,
        json={"section": 0, "paragraph": 0, "text": "Not there.", "replacement": "x"},
    )
    assert r.status_code == 422


def test_approval_needs_every_flag_resolved(ctx: tuple[TestClient, StubRepo]) -> None:
    client, repo = ctx
    card_id = repo.add(FLAGGED.model_dump(mode="json"))
    url = f"/editor/drafts/{card_id}/review"
    blocked = client.post(url, headers=H, json={"decision": "approved", "note": ""})
    assert blocked.status_code == 409
    client.post(
        f"/editor/drafts/{card_id}/sentence",
        headers=H,
        json={"section": 0, "paragraph": 0, "text": "Bad one.", "replacement": None},
    )
    ok = client.post(url, headers=H, json={"decision": "approved", "note": "good"})
    assert ok.status_code == 200
    assert (ok.json()["review_status"], ok.json()["review_note"]) == ("approved", "good")


def test_decided_draft_cannot_be_edited_or_decided_again(
    ctx: tuple[TestClient, StubRepo],
) -> None:
    client, repo = ctx
    card_id = repo.add(BODY.model_dump(mode="json"))
    url = f"/editor/drafts/{card_id}/review"
    assert (
        client.post(url, headers=H, json={"decision": "rejected", "note": "off topic"}).status_code
        == 200
    )
    assert client.post(url, headers=H, json={"decision": "approved"}).status_code == 409
    edit = {"section": 0, "paragraph": 0, "text": "P", "replacement": "Q"}
    assert (
        client.post(f"/editor/drafts/{card_id}/sentence", headers=H, json=edit).status_code == 409
    )


def test_failed_draft_cannot_be_approved_and_revise_is_allowed(
    ctx: tuple[TestClient, StubRepo],
) -> None:
    client, repo = ctx
    card_id = repo.add({})
    url = f"/editor/drafts/{card_id}/review"
    assert client.post(url, headers=H, json={"decision": "approved"}).status_code == 409
    assert (
        client.post(url, headers=H, json={"decision": "revise", "note": "redo"}).status_code == 200
    )


def test_review_routes_require_the_key(ctx: tuple[TestClient, StubRepo]) -> None:
    client, repo = ctx
    card_id = repo.add(BODY.model_dump(mode="json"))
    assert (
        client.post(f"/editor/drafts/{card_id}/review", json={"decision": "revise"}).status_code
        == 401
    )
