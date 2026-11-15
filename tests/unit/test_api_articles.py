import json
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import pytest
from apps.api.deps import get_article_repository, get_controls_repository, get_published_repository
from apps.api.main import create_app
from apps.api.routes import articles
from apps.api.schemas import PublicArticleOut, PublicArticleSummaryOut
from fastapi.testclient import TestClient
from pydantic import SecretStr

from signalforge.core.artifacts.article import (
    ArticleBody,
    ArticleClaim,
    ArticleCover,
    ArticleFlag,
    ArticleHeadline,
    ArticleSection,
    ArticleSource,
    FlagKind,
)
from signalforge.core.artifacts.research import ClaimStatus
from signalforge.core.config import Settings
from signalforge.image_storage import ImageStorageError

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
    sections=(ArticleSection(heading="H", paragraphs=("P", "P")),),
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
            review_log=[],
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


class StubPublished:
    def __init__(self) -> None:
        self.rows: dict[UUID, Any] = {}
        self.recent: list[datetime] = []  # publish times the pace check sees

    def slug_exists(self, slug: str) -> bool:
        return any(r.slug == slug for r in self.rows.values())

    def get_by_card(self, card_id: UUID) -> Any:
        return self.rows.get(card_id)

    def get_by_slug(self, slug: str) -> Any:
        return next((r for r in self.rows.values() if r.slug == slug), None)

    def get_public(self, slug: str) -> Any:
        row = self.get_by_slug(slug)
        return row if row is not None and row.status == "published" else None

    def list_public(self, limit: int) -> list[Any]:
        return [r for r in self.rows.values() if r.status == "published"][:limit]

    def published_times_since(self, since: datetime) -> list[datetime]:
        return sorted(t for t in self.recent if t >= since)

    def publish(self, card_id: UUID, fields: dict[str, Any]) -> Any:
        now = datetime(2026, 10, 21, tzinfo=UTC)
        row = self.rows.get(card_id) or SimpleNamespace(
            id=uuid4(), card_id=card_id, published_at=now
        )
        for name, value in fields.items():
            setattr(row, name, value)
        row.status, row.modified_at = "published", now
        self.rows[card_id] = row
        return row

    def set_images(self, row: Any, *, cover: Any, figure: Any) -> None:
        body = dict(row.body)
        if cover is not None:
            body["cover"] = {**body["cover"], "src": cover["src"], "alt": cover["alt"]}
        if figure is not None:
            body["figure"] = figure
        row.body = body

    def unpublish(self, row: Any) -> None:
        row.status = "unpublished"


@pytest.fixture
def ctx() -> Iterator[tuple[TestClient, StubRepo]]:
    app = create_app(Settings(_env_file=None, database_url=DSN, editor_api_key=KEY))  # type: ignore[call-arg,arg-type]
    repo = StubRepo()
    published = StubPublished()
    app.dependency_overrides[get_article_repository] = lambda: repo
    app.dependency_overrides[get_published_repository] = lambda: published
    repo.published = published  # type: ignore[attr-defined]
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


def published_row(body: ArticleBody, *, slug: str = "a-title", status: str = "published") -> Any:
    now = datetime(2026, 10, 21, tzinfo=UTC)
    return SimpleNamespace(
        id=uuid4(), card_id=uuid4(), slug=slug, status=status, seo_title="SEO title",
        meta_description="Meta.", byline="An Editor", process_note="Checked.",
        editor_analysis="", body=body.model_dump(mode="json"), published_at=now, modified_at=now,
    )  # fmt: skip


def test_public_shape_omits_editor_only_fields() -> None:
    dumped = PublicArticleOut.from_row(published_row(BODY)).model_dump(mode="json")
    leaked = _keys(dumped) & set(EDITOR_ONLY)
    assert leaked == set()
    schema = json.dumps(PublicArticleOut.model_json_schema())
    assert not [name for name in EDITOR_ONLY if f'"{name}"' in schema]
    assert dumped["claims"] == [{"text": "c", "status": "verified", "source_indices": [0]}]


COVERED = BODY.model_copy(
    update={
        "kind": "paper",
        "source_label": "arXiv",
        "headline": ArticleHeadline(
            value="81%", unit="on the test", direction="up", takeaway="A clause", claim_index=0
        ),
    }
)


def test_public_article_and_summary_expose_cover_facts_but_not_claim_index() -> None:
    row = published_row(COVERED)
    for out in (PublicArticleOut.from_row(row), PublicArticleSummaryOut.from_row(row)):
        dumped = out.model_dump(mode="json")
        assert dumped["kind"] == "paper"
        assert dumped["source_label"] == "arXiv"
        assert dumped["headline"] == {
            "value": "81%",
            "unit": "on the test",
            "direction": "up",
            "takeaway": "A clause",
        }


def test_old_bodies_give_null_cover_facts() -> None:
    row = published_row(BODY)
    old = {k: v for k, v in row.body.items() if k not in ("kind", "source_label", "headline")}
    row.body = old
    for out in (PublicArticleOut.from_row(row), PublicArticleSummaryOut.from_row(row)):
        dumped = out.model_dump(mode="json")
        assert (dumped["kind"], dumped["source_label"], dumped["headline"]) == (None, "", None)


def test_list_and_detail_routes_carry_cover_facts(ctx: tuple[TestClient, StubRepo]) -> None:
    client, repo = ctx
    card_id = approve(client, repo)
    client.post(f"/editor/drafts/{card_id}/publish", headers=H, json={})
    repo.published.rows[card_id].body = COVERED.model_dump(mode="json")  # type: ignore[attr-defined]
    assert client.get("/articles/title").json()["headline"]["value"] == "81%"
    listed = client.get("/articles").json()[0]
    assert listed["kind"] == "paper"
    assert listed["source_label"] == "arXiv"
    assert "claim_index" not in listed["headline"]


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


def approve(client: TestClient, repo: StubRepo, body: ArticleBody = BODY) -> UUID:
    card_id = repo.add(body.model_dump(mode="json"))
    r = client.post(f"/editor/drafts/{card_id}/review", headers=H, json={"decision": "approved"})
    assert r.status_code == 200
    return card_id


def test_publish_needs_an_approved_unflagged_draft(ctx: tuple[TestClient, StubRepo]) -> None:
    client, repo = ctx
    pending = repo.add(BODY.model_dump(mode="json"))
    assert client.post(f"/editor/drafts/{pending}/publish", headers=H, json={}).status_code == 409
    flagged = repo.add(FLAGGED.model_dump(mode="json"))
    repo.rows[flagged].review_status = "approved"
    assert client.post(f"/editor/drafts/{flagged}/publish", headers=H, json={}).status_code == 409
    assert client.post(f"/editor/drafts/{pending}/publish", json={}).status_code == 401


def test_publish_snapshots_the_body_and_defaults_the_seo_fields(
    ctx: tuple[TestClient, StubRepo],
) -> None:
    client, repo = ctx
    card_id = approve(client, repo)
    r = client.post(
        f"/editor/drafts/{card_id}/publish", headers=H, json={"editor_analysis": " Our take. "}
    )
    assert r.status_code == 200
    assert (r.json()["slug"], r.json()["status"]) == ("title", "published")
    saved = repo.published.rows[card_id]  # type: ignore[attr-defined]
    assert (saved.seo_title, saved.meta_description) == ("Title", "Dek")
    assert saved.editor_analysis == "Our take."
    assert saved.byline == "SignalForge Editorial"
    assert client.post(f"/editor/drafts/{card_id}/publish", headers=H, json={}).status_code == 409
    detail = client.get(f"/editor/drafts/{card_id}", headers=H).json()
    assert detail["published_slug"] == "title"


def test_publish_slug_is_unique_and_validated(ctx: tuple[TestClient, StubRepo]) -> None:
    client, repo = ctx
    first, second = approve(client, repo), approve(client, repo)
    assert (
        client.post(f"/editor/drafts/{first}/publish", headers=H, json={}).json()["slug"] == "title"
    )
    auto = client.post(f"/editor/drafts/{second}/publish", headers=H, json={})
    assert auto.json()["slug"] == "title-2"
    third = approve(client, repo)
    taken = client.post(f"/editor/drafts/{third}/publish", headers=H, json={"slug": "title"})
    assert taken.status_code == 409
    bad = client.post(f"/editor/drafts/{third}/publish", headers=H, json={"slug": "Bad Slug!"})
    assert bad.status_code == 422


def test_public_routes_serve_only_published_and_hide_editor_fields(
    ctx: tuple[TestClient, StubRepo],
) -> None:
    client, repo = ctx
    card_id = approve(client, repo)
    assert client.get("/articles/title").status_code == 404
    client.post(f"/editor/drafts/{card_id}/publish", headers=H, json={})
    article = client.get("/articles/title")
    assert article.status_code == 200
    assert _keys(article.json()) & set(EDITOR_ONLY) == set()
    assert [a["slug"] for a in client.get("/articles").json()] == ["title"]
    client.post("/editor/articles/title/unpublish", headers=H)
    assert client.get("/articles/title").status_code == 404
    assert client.get("/articles").json() == []
    assert client.post("/editor/articles/title/unpublish").status_code == 401


def test_unpublished_article_can_be_republished_at_the_same_slug(
    ctx: tuple[TestClient, StubRepo],
) -> None:
    client, repo = ctx
    card_id = approve(client, repo)
    client.post(f"/editor/drafts/{card_id}/publish", headers=H, json={})
    client.post("/editor/articles/title/unpublish", headers=H)
    again = client.post(f"/editor/drafts/{card_id}/publish", headers=H, json={})
    assert (again.status_code, again.json()["slug"]) == (200, "title")
    assert client.get("/articles/title").status_code == 200


def test_publish_pings_indexnow_only_when_configured(
    ctx: tuple[TestClient, StubRepo], monkeypatch: pytest.MonkeyPatch
) -> None:
    pings: list[tuple[str, str, str]] = []
    monkeypatch.setattr(articles, "ping_indexnow", lambda *a: pings.append(a))
    client, repo = ctx
    client.post(f"/editor/drafts/{approve(client, repo)}/publish", headers=H, json={})
    assert pings == []

    app = client.app
    app.state.settings = app.state.settings.model_copy(  # type: ignore[attr-defined]
        update={"site_url": "https://example.com", "indexnow_key": "k"}
    )
    client.post(f"/editor/drafts/{approve(client, repo)}/publish", headers=H, json={})
    assert len(pings) == 1
    assert pings[0][:2] == ("https://example.com", "k")


BUCKET = "https://proj.supabase.co/storage/v1/object/public/article-images"


def test_attach_images_stores_cover_and_figure_and_exposes_them(
    ctx: tuple[TestClient, StubRepo],
) -> None:
    client, repo = ctx
    client.app.state.settings = client.app.state.settings.model_copy(  # type: ignore[attr-defined]
        update={"supabase_url": "https://proj.supabase.co"}
    )
    card_id = approve(client, repo)
    slug = client.post(f"/editor/drafts/{card_id}/publish", headers=H, json={}).json()["slug"]
    payload = {
        "cover": {"src": f"{BUCKET}/{slug}/cover.svg", "alt": "Cover alt"},
        "figure": {"src": f"{BUCKET}/{slug}/figure.svg", "alt": "Figure alt", "caption": "Cap"},
    }
    assert client.post(f"/editor/articles/{slug}/images", json=payload).status_code == 401
    ok = client.post(f"/editor/articles/{slug}/images", headers=H, json=payload)
    assert ok.status_code == 200
    public = client.get(f"/articles/{slug}").json()
    assert public["cover"]["src"] == f"{BUCKET}/{slug}/cover.svg"
    assert public["figure"] == {
        "src": f"{BUCKET}/{slug}/figure.svg",
        "alt": "Figure alt",
        "caption": "Cap",
    }


@pytest.mark.parametrize(
    "src",
    [
        "http://proj.supabase.co/storage/v1/object/public/article-images/a.svg",
        "https://evil.example/storage/v1/object/public/article-images/a.svg",
        "https://proj.supabase.co/storage/v1/object/public/other/a.svg",
        "https://proj.supabase.co/storage/v1/object/public/article-images/a.svg?x=1",
    ],
)
def test_attach_images_rejects_foreign_urls(ctx: tuple[TestClient, StubRepo], src: str) -> None:
    client, repo = ctx
    client.app.state.settings = client.app.state.settings.model_copy(  # type: ignore[attr-defined]
        update={"supabase_url": "https://proj.supabase.co"}
    )
    slug = client.post(
        f"/editor/drafts/{approve(client, repo)}/publish", headers=H, json={}
    ).json()["slug"]
    r = client.post(
        f"/editor/articles/{slug}/images", headers=H, json={"cover": {"src": src, "alt": "a"}}
    )
    assert r.status_code == 422


def test_attach_images_needs_supabase_configured_and_known_article(
    ctx: tuple[TestClient, StubRepo],
) -> None:
    client, repo = ctx
    slug = client.post(
        f"/editor/drafts/{approve(client, repo)}/publish", headers=H, json={}
    ).json()["slug"]
    body = {"cover": {"src": f"{BUCKET}/a.svg", "alt": "a"}}
    assert client.post(f"/editor/articles/{slug}/images", headers=H, json=body).status_code == 422
    assert client.post("/editor/articles/nope/images", headers=H, json=body).status_code == 404


SVG = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 9 9"><rect width="9" height="9"/></svg>'


def _upload_body(cover: str = SVG, figure: str = SVG) -> dict[str, object]:
    return {
        "cover": {"svg": cover, "alt": "Cover alt"},
        "figure": {"svg": figure, "alt": "Figure alt", "caption": "Cap"},
    }


def _configure_upload(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str]]:
    client.app.state.settings = client.app.state.settings.model_copy(  # type: ignore[attr-defined]
        update={
            "supabase_url": "https://proj.supabase.co",
            "supabase_secret_key": SecretStr("service-key"),
        }
    )
    sent: list[tuple[str, str]] = []

    def fake(_svg: str, *, slug: str, role: str, supabase_url: str, key: str) -> str:
        assert supabase_url == "https://proj.supabase.co"
        sent.append((role, key))
        return f"{BUCKET}/{slug}/{role}-abc.svg"

    monkeypatch.setattr(articles, "upload_svg", fake)
    return sent


def test_upload_images_stores_svgs_with_the_server_key_and_attaches_them(
    ctx: tuple[TestClient, StubRepo], monkeypatch: pytest.MonkeyPatch
) -> None:
    client, repo = ctx
    sent = _configure_upload(client, monkeypatch)
    slug = client.post(
        f"/editor/drafts/{approve(client, repo)}/publish", headers=H, json={}
    ).json()["slug"]
    url = f"/editor/articles/{slug}/images/upload"
    assert client.post(url, json=_upload_body()).status_code == 401
    ok = client.post(url, headers=H, json=_upload_body())
    assert ok.status_code == 200
    assert sent == [("cover", "service-key"), ("figure", "service-key")]
    public = client.get(f"/articles/{slug}").json()
    assert public["cover"]["src"] == f"{BUCKET}/{slug}/cover-abc.svg"
    assert public["figure"]["caption"] == "Cap"


@pytest.mark.parametrize(
    "svg",
    [
        "<html></html>",
        '<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>',
        '<svg xmlns="http://www.w3.org/2000/svg" onload="x()"></svg>',
        '<svg xmlns="http://www.w3.org/2000/svg"><image href="https://evil.example/a.png"/></svg>',
    ],
)
def test_upload_images_refuses_unsafe_svg(
    ctx: tuple[TestClient, StubRepo], monkeypatch: pytest.MonkeyPatch, svg: str
) -> None:
    client, repo = ctx
    sent = _configure_upload(client, monkeypatch)
    slug = client.post(
        f"/editor/drafts/{approve(client, repo)}/publish", headers=H, json={}
    ).json()["slug"]
    r = client.post(f"/editor/articles/{slug}/images/upload", headers=H, json=_upload_body(svg))
    assert r.status_code == 422
    assert sent == []


def test_upload_images_needs_configuration_and_a_known_article(
    ctx: tuple[TestClient, StubRepo], monkeypatch: pytest.MonkeyPatch
) -> None:
    client, repo = ctx
    slug = client.post(
        f"/editor/drafts/{approve(client, repo)}/publish", headers=H, json={}
    ).json()["slug"]
    url = f"/editor/articles/{slug}/images/upload"
    assert client.post(url, headers=H, json=_upload_body()).status_code == 503
    _configure_upload(client, monkeypatch)
    missing = "/editor/articles/nope/images/upload"
    assert client.post(missing, headers=H, json=_upload_body()).status_code == 404


def test_upload_images_reports_a_storage_failure_as_bad_gateway(
    ctx: tuple[TestClient, StubRepo], monkeypatch: pytest.MonkeyPatch
) -> None:
    client, repo = ctx
    _configure_upload(client, monkeypatch)

    def boom(*_a: object, **_k: object) -> str:
        raise ImageStorageError("Storage rejected the upload (400)")

    monkeypatch.setattr(articles, "upload_svg", boom)
    slug = client.post(
        f"/editor/drafts/{approve(client, repo)}/publish", headers=H, json={}
    ).json()["slug"]
    r = client.post(f"/editor/articles/{slug}/images/upload", headers=H, json=_upload_body())
    assert r.status_code == 502
    assert "service-key" not in r.text


AGENT_KEY = "agent-secret-value"
HA = {"X-Editor-Key": AGENT_KEY}


@pytest.fixture
def actx() -> Iterator[tuple[TestClient, StubRepo]]:
    app = create_app(
        Settings(  # type: ignore[call-arg]
            _env_file=None,
            database_url=DSN,  # type: ignore[arg-type]
            editor_api_key=KEY,  # type: ignore[arg-type]
            agent_api_key=AGENT_KEY,  # type: ignore[arg-type]
            auto_review_min_words=1,
            auto_review_min_claims=1,
        )
    )
    repo = StubRepo()
    published = StubPublished()
    app.dependency_overrides[get_article_repository] = lambda: repo
    controls = SimpleNamespace(
        get=lambda: SimpleNamespace(paused=False, paused_until=None, paused_reason=None)
    )
    app.dependency_overrides[get_published_repository] = lambda: published
    app.dependency_overrides[get_controls_repository] = lambda: controls
    repo.published = published  # type: ignore[attr-defined]
    repo.controls = controls  # type: ignore[attr-defined]
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client, repo


def test_agent_key_works_on_editor_endpoints_and_wrong_keys_do_not(
    actx: tuple[TestClient, StubRepo],
) -> None:
    client, repo = actx
    card_id = repo.add(BODY.model_dump(mode="json"))
    assert client.get(f"/editor/drafts/{card_id}", headers=HA).status_code == 200
    assert client.get(f"/editor/drafts/{card_id}", headers=H).status_code == 200
    assert (
        client.get(f"/editor/drafts/{card_id}", headers={"X-Editor-Key": "nope"}).status_code == 401
    )
    assert client.get("/agent/runs").status_code == 401
    assert client.get("/agent/runs", headers=HA).status_code == 200


def _pause(repo: StubRepo) -> None:
    repo.controls.get = lambda: SimpleNamespace(  # type: ignore[attr-defined]
        paused=True, paused_until=None, paused_reason="drill"
    )


def test_agent_key_cannot_publish_while_paused(actx: tuple[TestClient, StubRepo]) -> None:
    client, repo = actx
    card_id = _approve_without_publishing(client, repo)
    _pause(repo)
    r = client.post(f"/editor/drafts/{card_id}/publish", headers=HA, json={})
    assert r.status_code == 423
    assert repo.published.get_by_card(card_id) is None  # type: ignore[attr-defined]


def test_editor_key_publishes_while_paused(actx: tuple[TestClient, StubRepo]) -> None:
    client, repo = actx
    card_id = _approve_without_publishing(client, repo)
    _pause(repo)
    r = client.post(f"/editor/drafts/{card_id}/publish", headers=H, json={})
    assert (r.status_code, r.json()["status"]) == (200, "published")


def test_agent_key_publishes_when_running(actx: tuple[TestClient, StubRepo]) -> None:
    client, repo = actx
    card_id = _approve_without_publishing(client, repo)
    r = client.post(f"/editor/drafts/{card_id}/publish", headers=HA, json={})
    assert (r.status_code, r.json()["status"]) == (200, "published")


def test_agent_key_cannot_republish_an_unpublished_article(
    actx: tuple[TestClient, StubRepo],
) -> None:
    client, repo = actx
    card_id = _approve_without_publishing(client, repo)
    client.post(f"/editor/drafts/{card_id}/publish", headers=H, json={})
    client.post("/editor/articles/title/unpublish", headers=H)
    r = client.post(f"/editor/drafts/{card_id}/publish", headers=HA, json={})
    assert r.status_code == 409
    assert (
        r.json()["error"]["message"]
        == "Unpublished by the owner; only the editor key can republish"
    )
    assert repo.published.get_by_card(card_id).status == "unpublished"  # type: ignore[attr-defined]


def test_editor_key_republishes_an_unpublished_article(
    actx: tuple[TestClient, StubRepo],
) -> None:
    client, repo = actx
    card_id = _approve_without_publishing(client, repo)
    client.post(f"/editor/drafts/{card_id}/publish", headers=H, json={})
    client.post("/editor/articles/title/unpublish", headers=H)
    r = client.post(f"/editor/drafts/{card_id}/publish", headers=H, json={})
    assert (r.status_code, r.json()["status"]) == (200, "published")


def test_run_stage_starts_in_the_background_and_reports_busy(
    actx: tuple[TestClient, StubRepo], monkeypatch: pytest.MonkeyPatch
) -> None:
    from apps.api import agent_runs

    started: list[tuple[str, int, bool]] = []

    def fake_start(stage: str, _settings: object, limit: int, retry: bool) -> bool:
        started.append((stage, limit, retry))
        return True

    monkeypatch.setattr(agent_runs, "start", fake_start)
    client, _ = actx
    r = client.post("/agent/run/draft?limit=3&retry_failed=true", headers=HA)
    assert (r.status_code, r.json()) == (202, {"started": True, "stage": "draft"})
    assert started == [("draft", 3, True)]
    assert client.post("/agent/run/bogus", headers=HA).status_code == 422
    monkeypatch.setattr(agent_runs, "start", lambda *_a: False)
    assert client.post("/agent/run/tick", headers=HA).status_code == 409


def test_auto_review_approves_and_publishes_with_the_actor_logged(
    actx: tuple[TestClient, StubRepo],
) -> None:
    client, repo = actx
    card_id = repo.add(BODY.model_dump(mode="json"))
    r = client.post(f"/agent/drafts/{card_id}/auto-review?publish=true", headers=HA)
    assert r.status_code == 200
    out = r.json()
    assert (out["action"], out["reasons"]) == ("approve", [])
    assert out["published"]["status"] == "published"
    assert repo.rows[card_id].review_status == "approved"
    assert repo.rows[card_id].log[-1]["actor"] == "agent"
    assert client.post(f"/agent/drafts/{card_id}/auto-review", headers=HA).status_code == 409


def test_auto_review_sends_a_thin_draft_back_with_the_reasons(
    actx: tuple[TestClient, StubRepo],
) -> None:
    client, repo = actx
    client.app.state.settings = client.app.state.settings.model_copy(  # type: ignore[attr-defined]
        update={"auto_review_min_words": 500}
    )
    card_id = repo.add(BODY.model_dump(mode="json"))
    out = client.post(f"/agent/drafts/{card_id}/auto-review", headers=HA).json()
    assert out["action"] == "revise"
    assert "words" in out["reasons"][0]
    assert repo.rows[card_id].review_status == "revise"
    assert "words" in repo.rows[card_id].review_note


def test_auto_review_counts_a_failed_redraft_toward_the_cap(
    actx: tuple[TestClient, StubRepo],
) -> None:
    client, repo = actx
    client.app.state.settings = client.app.state.settings.model_copy(  # type: ignore[attr-defined]
        update={"auto_review_min_words": 500, "auto_review_max_redrafts": 2}
    )
    card_id = repo.add(BODY.model_dump(mode="json"))
    repo.rows[card_id].review_log = [{"type": "redraft_failed"}, {"type": "redraft"}]
    out = client.post(f"/agent/drafts/{card_id}/auto-review", headers=HA).json()
    assert out["action"] == "reject"
    assert repo.rows[card_id].review_status == "rejected"


def _approve_without_publishing(client: TestClient, repo: StubRepo) -> UUID:
    card_id = repo.add(BODY.model_dump(mode="json"))
    out = client.post(f"/agent/drafts/{card_id}/auto-review", headers=HA).json()
    assert out["action"] == "approve"
    return card_id


def test_auto_review_while_paused_approves_without_publishing(
    actx: tuple[TestClient, StubRepo],
) -> None:
    client, repo = actx
    repo.controls.get = lambda: SimpleNamespace(  # type: ignore[attr-defined]
        paused=True, paused_until=None, paused_reason="drill"
    )
    card_id = repo.add(BODY.model_dump(mode="json"))
    out = client.post(f"/agent/drafts/{card_id}/auto-review?publish=true", headers=HA).json()
    assert out["action"] == "approve"
    assert (out["published"], out["queued"]) == (None, True)
    assert repo.rows[card_id].review_status == "approved"


def test_auto_review_holds_a_publish_that_is_too_soon_after_the_last(
    actx: tuple[TestClient, StubRepo],
) -> None:
    client, repo = actx
    repo.published.recent = [datetime.now(UTC) - timedelta(minutes=30)]  # type: ignore[attr-defined]
    card_id = repo.add(BODY.model_dump(mode="json"))
    out = client.post(f"/agent/drafts/{card_id}/auto-review?publish=true", headers=HA).json()
    assert out["action"] == "approve"
    assert out["published"] is None
    assert out["queued"] is True
    assert out["next_publish_at"] is not None
    assert repo.rows[card_id].review_status == "approved"  # saved, waiting for a slot


def test_auto_review_holds_a_publish_over_the_daily_cap(
    actx: tuple[TestClient, StubRepo],
) -> None:
    client, repo = actx
    now = datetime.now(UTC)
    repo.published.recent = [now - timedelta(hours=h) for h in (20, 14, 8)]  # type: ignore[attr-defined]
    card_id = repo.add(BODY.model_dump(mode="json"))
    out = client.post(f"/agent/drafts/{card_id}/auto-review?publish=true", headers=HA).json()
    assert (out["queued"], out["published"]) == (True, None)


def _waiting(monkeypatch: pytest.MonkeyPatch, *card_ids: UUID) -> None:
    from apps.api.routes import agent as agent_routes

    cards = [
        agent_routes.PipelineCardOut(
            card_id=c, title="t", stage="approved", next_action="publish", slug=None
        )
        for c in card_ids  # newest first, like the real list
    ]
    monkeypatch.setattr(agent_routes, "_cards", lambda *_a: cards)


def test_publish_next_publishes_the_longest_waiting_draft(
    actx: tuple[TestClient, StubRepo], monkeypatch: pytest.MonkeyPatch
) -> None:
    client, repo = actx
    older = _approve_without_publishing(client, repo)
    newer = _approve_without_publishing(client, repo)
    _waiting(monkeypatch, newer, older)
    out = client.post("/agent/publish-next", headers=HA).json()
    assert out["published"]["status"] == "published"
    assert out["waiting"] == 1
    assert repo.published.get_by_card(older) is not None  # type: ignore[attr-defined]
    assert repo.published.get_by_card(newer) is None  # type: ignore[attr-defined]


def test_publish_next_waits_for_the_pace_and_says_when(
    actx: tuple[TestClient, StubRepo], monkeypatch: pytest.MonkeyPatch
) -> None:
    client, repo = actx
    card_id = _approve_without_publishing(client, repo)
    _waiting(monkeypatch, card_id)
    repo.published.recent = [datetime.now(UTC) - timedelta(minutes=10)]  # type: ignore[attr-defined]
    out = client.post("/agent/publish-next", headers=HA).json()
    assert out["published"] is None
    assert out["waiting"] == 1
    assert out["next_publish_at"] is not None


def test_publish_next_with_nothing_waiting_does_nothing(
    actx: tuple[TestClient, StubRepo], monkeypatch: pytest.MonkeyPatch
) -> None:
    client, _ = actx
    _waiting(monkeypatch)
    out = client.post("/agent/publish-next", headers=HA).json()
    assert out == {"published": None, "waiting": 0, "next_publish_at": None}
    assert client.post("/agent/publish-next").status_code == 401


def test_research_runs_one_card_by_default_and_other_stages_ten(
    actx: tuple[TestClient, StubRepo], monkeypatch: pytest.MonkeyPatch
) -> None:
    from apps.api import agent_runs

    seen: list[tuple[str, int]] = []

    def fake_start(stage: str, _settings: object, limit: int, _retry: bool) -> bool:
        seen.append((stage, limit))
        return True

    monkeypatch.setattr(agent_runs, "start", fake_start)
    client, _ = actx
    for stage in ("research", "draft"):
        assert client.post(f"/agent/run/{stage}", headers=HA).status_code == 202
    assert client.post("/agent/run/research?limit=4", headers=HA).status_code == 202
    assert seen == [("research", 1), ("draft", 10), ("research", 4)]


def test_force_publishes_past_the_pace(
    actx: tuple[TestClient, StubRepo], monkeypatch: pytest.MonkeyPatch
) -> None:
    client, repo = actx
    now = datetime.now(UTC)
    repo.published.recent = [now - timedelta(minutes=5)] * 3  # type: ignore[attr-defined]
    held = repo.add(BODY.model_dump(mode="json"))
    queued = client.post(f"/agent/drafts/{held}/auto-review?publish=true", headers=HA).json()
    assert queued["queued"] is True
    hot = repo.add(BODY.model_dump(mode="json"))
    out = client.post(f"/agent/drafts/{hot}/auto-review?publish=true&force=true", headers=HA).json()
    assert out["published"]["status"] == "published"
    assert out["queued"] is False
    _waiting(monkeypatch, held)
    assert client.post("/agent/publish-next", headers=HA).json()["published"] is None
    forced = client.post("/agent/publish-next?force=true", headers=HA).json()
    assert forced["published"]["status"] == "published"


def test_publish_next_can_pick_one_waiting_draft(
    actx: tuple[TestClient, StubRepo], monkeypatch: pytest.MonkeyPatch
) -> None:
    client, repo = actx
    first = _approve_without_publishing(client, repo)
    second = _approve_without_publishing(client, repo)
    _waiting(monkeypatch, second, first)
    out = client.post(f"/agent/publish-next?card_id={second}", headers=HA).json()
    assert out["published"]["status"] == "published"
    assert repo.published.get_by_card(second) is not None  # type: ignore[attr-defined]
    assert repo.published.get_by_card(first) is None  # type: ignore[attr-defined]
    stranger = uuid4()
    assert client.post(f"/agent/publish-next?card_id={stranger}", headers=HA).status_code == 404


def _run_jobs_inline(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    from apps.api import agent_runs
    from apps.worker import topic as topic_job

    calls: list[dict[str, Any]] = []

    def fake_run(_engine: object, _settings: object, **kwargs: Any) -> dict[str, Any]:
        calls.append(kwargs)
        return {"ok": True}

    def fake_start(stage: str, job: Any) -> bool:
        assert stage == "topic"
        job()
        return True

    engine = SimpleNamespace(dispose=lambda: None)
    monkeypatch.setattr(topic_job, "run", fake_run)
    monkeypatch.setattr(agent_runs, "start_job", fake_start)
    monkeypatch.setattr("apps.api.routes.agent.create_db_engine", lambda *_a: engine)
    return calls


def test_a_topic_by_url_or_text_starts_the_job_with_its_flags(
    actx: tuple[TestClient, StubRepo], monkeypatch: pytest.MonkeyPatch
) -> None:
    client, _ = actx
    calls = _run_jobs_inline(monkeypatch)
    by_url = {"url": "https://example.com/post?utm_source=x", "note": "angle", "hot": True}
    r = client.post("/agent/topics", headers=HA, json=by_url)
    assert (r.status_code, r.json()) == (202, {"started": True, "stage": "topic"})
    assert (
        client.post("/agent/topics", headers=HA, json={"query": "mamba 3 benchmarks"}).status_code
        == 202
    )
    assert calls == [
        {
            "url": "https://example.com/post?utm_source=x",
            "query": None,
            "note": "angle",
            "hot": True,
        },
        {"url": None, "query": "mamba 3 benchmarks", "note": "", "hot": False},
    ]


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"url": "https://example.com/a", "query": "both given"},
        {"url": "ftp://example.com/a"},
        {"url": "not a url"},
        {"query": "ab"},
        {"query": "fine query", "hot": "maybe"},
        {"query": "fine query", "extra": 1},
    ],
)
def test_a_bad_topic_is_refused(actx: tuple[TestClient, StubRepo], body: dict[str, Any]) -> None:
    client, _ = actx
    assert client.post("/agent/topics", headers=HA, json=body).status_code == 422


def test_a_topic_needs_a_key_and_a_free_pipeline(
    actx: tuple[TestClient, StubRepo], monkeypatch: pytest.MonkeyPatch
) -> None:
    from apps.api import agent_runs

    client, _ = actx
    assert client.post("/agent/topics", json={"query": "fine query"}).status_code == 401
    monkeypatch.setattr(agent_runs, "start_job", lambda *_a: False)
    assert client.post("/agent/topics", headers=HA, json={"query": "fine query"}).status_code == 409


def test_a_topic_is_refused_while_paused(
    actx: tuple[TestClient, StubRepo], monkeypatch: pytest.MonkeyPatch
) -> None:
    from apps.api import agent_runs

    client, repo = actx
    started: list[object] = []

    def start_job(*args: object) -> bool:
        started.append(args)
        return True

    monkeypatch.setattr(agent_runs, "start_job", start_job)
    repo.controls.get = lambda: SimpleNamespace(  # type: ignore[attr-defined]
        paused=True, paused_until=None, paused_reason="drill"
    )
    r = client.post("/agent/topics", headers=HA, json={"query": "fine query", "hot": True})
    assert r.status_code == 423
    assert started == []


def test_a_published_table_reaches_the_public_article_with_its_source(
    ctx: tuple[TestClient, StubRepo],
) -> None:
    client, repo = ctx
    body = BODY.model_dump(mode="json")
    body["sections"][0]["table"] = {
        "caption": "Scores",
        "header": ["Model", "Score"],
        "rows": [["A", "91"], ["B", "88"]],
        "source_index": 0,
    }
    card_id = repo.add(body)
    client.post(f"/editor/drafts/{card_id}/review", headers=H, json={"decision": "approved"})
    slug = client.post(f"/editor/drafts/{card_id}/publish", headers=H, json={}).json()["slug"]
    sections = client.get(f"/articles/{slug}").json()["sections"]
    assert sections[0]["table"] == {
        "caption": "Scores",
        "header": ["Model", "Score"],
        "rows": [["A", "91"], ["B", "88"]],
        "source": {"label": "example", "url": "https://example.com"},
    }
    assert all(section["table"] is None for section in sections[1:])


def test_a_table_whose_source_is_missing_still_shows_without_one(
    ctx: tuple[TestClient, StubRepo],
) -> None:
    client, repo = ctx
    body = BODY.model_dump(mode="json")
    body["sections"][0]["table"] = {
        "caption": "",
        "header": ["A", "B"],
        "rows": [["1", "2"], ["3", "4"]],
        "source_index": 9,
    }
    card_id = repo.add(body)
    client.post(f"/editor/drafts/{card_id}/review", headers=H, json={"decision": "approved"})
    slug = client.post(f"/editor/drafts/{card_id}/publish", headers=H, json={}).json()["slug"]
    table = client.get(f"/articles/{slug}").json()["sections"][0]["table"]
    assert table["source"] is None
    assert table["rows"] == [["1", "2"], ["3", "4"]]


def test_policy_approved_article_says_automated_checks_approved_it(
    ctx: tuple[TestClient, StubRepo],
) -> None:
    client, repo = ctx
    card_id = repo.add(BODY.model_dump(mode="json"))
    repo.rows[card_id].review_status = "approved"
    repo.rows[card_id].review_note = "approved by policy"
    assert client.post(f"/editor/drafts/{card_id}/publish", headers=H, json={}).status_code == 200
    saved = repo.published.rows[card_id]  # type: ignore[attr-defined]
    assert "not an editor" in saved.process_note
    assert "An editor reviewed" not in saved.process_note


def test_editor_approved_article_keeps_the_editor_note(ctx: tuple[TestClient, StubRepo]) -> None:
    client, repo = ctx
    card_id = approve(client, repo)
    assert client.post(f"/editor/drafts/{card_id}/publish", headers=H, json={}).status_code == 200
    saved = repo.published.rows[card_id]  # type: ignore[attr-defined]
    assert "An editor reviewed and approved" in saved.process_note
