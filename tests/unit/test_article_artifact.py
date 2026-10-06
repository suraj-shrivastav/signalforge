from uuid import uuid4

import pytest
from pydantic import ValidationError

from signalforge.core.artifacts.article import (
    ArticleBody,
    ArticleClaim,
    ArticleCover,
    ArticleDraft,
    ArticleSection,
    ArticleSource,
    ArticleTemplate,
    DraftStatus,
)
from signalforge.core.artifacts.research import ClaimStatus


def make_section(**overrides: object) -> ArticleSection:
    fields: dict[str, object] = {"heading": "The short version", "paragraphs": ["One.", "Two."]}
    return ArticleSection(**{**fields, **overrides})  # type: ignore[arg-type]


def make_claim(**overrides: object) -> ArticleClaim:
    fields: dict[str, object] = {
        "text": "X does Y.",
        "evidence_span": "X does Y",
        "document_indices": [0, 1],
    }
    return ArticleClaim(**{**fields, **overrides})  # type: ignore[arg-type]


def make_source(**overrides: object) -> ArticleSource:
    fields: dict[str, object] = {"label": "Example blog", "url": "https://example.com/post"}
    return ArticleSource(**{**fields, **overrides})  # type: ignore[arg-type]


def make_cover(**overrides: object) -> ArticleCover:
    fields: dict[str, object] = {"alt": "Abstract grid of squares"}
    return ArticleCover(**{**fields, **overrides})  # type: ignore[arg-type]


def make_body(**overrides: object) -> ArticleBody:
    fields: dict[str, object] = {
        "title": "A title",
        "dek": "A dek.",
        "sections": [make_section()],
        "cover": make_cover(),
    }
    return ArticleBody(**{**fields, **overrides})  # type: ignore[arg-type]


def make(**overrides: object) -> ArticleDraft:
    fields: dict[str, object] = {"card_id": uuid4(), "template": "explainer"}
    return ArticleDraft(**{**fields, **overrides})  # type: ignore[arg-type]


def test_enum_values() -> None:
    assert [s.value for s in DraftStatus] == ["drafting", "drafted", "needs_more_info", "failed"]
    assert [t.value for t in ArticleTemplate] == [
        "news_brief",
        "explainer",
        "paper_breakdown",
        "comparison",
    ]


def test_draft_defaults() -> None:
    draft = make()
    assert draft.status is DraftStatus.DRAFTING
    assert draft.template is ArticleTemplate.EXPLAINER
    assert draft.draft is None
    assert draft.review_summary == ""
    assert draft.schema_version == ArticleDraft.SCHEMA_VERSION


def test_draft_holds_nested_models() -> None:
    body = make_body(claims=[make_claim(status="verified")], sources=[make_source()])
    draft = make(status="drafted", draft=body)
    assert draft.status is DraftStatus.DRAFTED
    assert draft.draft is not None
    assert draft.draft.sections[0].paragraphs == ("One.", "Two.")
    assert draft.draft.claims[0].status is ClaimStatus.VERIFIED
    assert draft.draft.sources[0].label == "Example blog"


def test_draft_round_trips_through_json() -> None:
    draft = make(status="drafted", draft=make_body(claims=[make_claim()]))
    assert ArticleDraft.model_validate(draft.model_dump(mode="json")) == draft


def test_failed_draft_may_have_no_body() -> None:
    assert make(status="failed").draft is None


def test_body_defaults() -> None:
    body = make_body()
    assert body.claims == ()
    assert body.sources == ()


def test_claim_defaults_to_unverified() -> None:
    claim = make_claim()
    assert claim.status is ClaimStatus.UNVERIFIED
    assert claim.document_indices == (0, 1)


def test_cover_optional_fields() -> None:
    cover = make_cover()
    assert cover.src is None
    assert cover.credit is None


@pytest.mark.parametrize(
    ("instance", "field", "value"),
    [
        (make(), "status", DraftStatus.DRAFTED),
        (make_body(), "title", "Other"),
        (make_section(), "heading", "Other"),
        (make_claim(), "status", ClaimStatus.VERIFIED),
        (make_source(), "url", "https://example.org"),
        (make_cover(), "alt", "Other"),
    ],
)
def test_frozen(instance: object, field: str, value: object) -> None:
    with pytest.raises(ValidationError):
        setattr(instance, field, value)


@pytest.mark.parametrize(
    "overrides",
    [
        {"status": "done"},
        {"template": "Explainer"},
        {"template": "listicle"},
        {"status": "drafted"},
        {"draft": {"title": "T"}},
        {"extra": 1},
    ],
)
def test_invalid_draft_rejected(overrides: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        make(**overrides)


def test_template_is_required() -> None:
    with pytest.raises(ValidationError):
        ArticleDraft(card_id=uuid4())  # type: ignore[call-arg]


@pytest.mark.parametrize(
    "overrides",
    [
        {"title": ""},
        {"dek": ""},
        {"sections": []},
        {"cover": None},
        {"sources": [{"label": "X"}]},
        {"extra": 1},
    ],
)
def test_invalid_body_rejected(overrides: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        make_body(**overrides)


@pytest.mark.parametrize(
    "overrides",
    [{"heading": ""}, {"paragraphs": []}, {"paragraphs": [""]}, {"extra": 1}],
)
def test_invalid_section_rejected(overrides: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        make_section(**overrides)


@pytest.mark.parametrize(
    "overrides",
    [
        {"text": ""},
        {"evidence_span": ""},
        {"document_indices": []},
        {"document_indices": [0, -1]},
        {"status": "true"},
        {"extra": 1},
    ],
)
def test_invalid_claim_rejected(overrides: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        make_claim(**overrides)


@pytest.mark.parametrize("overrides", [{"label": ""}, {"url": ""}, {"extra": 1}])
def test_invalid_source_rejected(overrides: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        make_source(**overrides)


@pytest.mark.parametrize("overrides", [{"alt": ""}, {"alt": None}, {"extra": 1}])
def test_invalid_cover_rejected(overrides: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        make_cover(**overrides)
