from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from signalforge.core.artifacts.research import (
    ClaimStatus,
    ResearchClaim,
    ResearchDocument,
    ResearchPackage,
    ResearchStatus,
)


def make_document(**overrides: object) -> ResearchDocument:
    fields: dict[str, object] = {
        "url": "https://example.com/post",
        "title": "A post",
        "source_label": "Example",
        "is_primary": True,
        "raw_text_ref": "sha256:abc",
        "text": "A post body.",
        "fetched_at": datetime(2026, 9, 27, 12, 0, tzinfo=UTC),
    }
    return ResearchDocument(**{**fields, **overrides})  # type: ignore[arg-type]


def make_claim(**overrides: object) -> ResearchClaim:
    fields: dict[str, object] = {
        "text": "X does Y.",
        "evidence_span": "X does Y",
        "document_indices": [0, 2],
    }
    return ResearchClaim(**{**fields, **overrides})  # type: ignore[arg-type]


def make(**overrides: object) -> ResearchPackage:
    fields: dict[str, object] = {"card_id": uuid4()}
    return ResearchPackage(**{**fields, **overrides})  # type: ignore[arg-type]


def test_enum_values() -> None:
    assert [s.value for s in ResearchStatus] == [
        "researching",
        "researched",
        "needs_more_info",
        "failed",
    ]
    assert [s.value for s in ClaimStatus] == [
        "verified",
        "supported",
        "uncertain",
        "conflicting",
        "unverified",
    ]


def test_package_defaults() -> None:
    package = make()
    assert package.status is ResearchStatus.RESEARCHING
    assert package.documents == ()
    assert package.claims == ()
    assert package.gaps_and_disagreements == ""
    assert package.schema_version == ResearchPackage.SCHEMA_VERSION


def test_package_holds_nested_models() -> None:
    package = make(documents=[make_document()], claims=[make_claim()], status="researched")
    assert package.status is ResearchStatus.RESEARCHED
    assert package.documents[0].is_primary is True
    assert package.claims[0].document_indices == (0, 2)


def test_document_valid() -> None:
    document = make_document()
    assert document.fetched_at.tzinfo is UTC
    assert document.raw_text_ref == "sha256:abc"


def test_claim_defaults_to_unverified() -> None:
    claim = make_claim()
    assert claim.status is ClaimStatus.UNVERIFIED
    assert claim.document_indices == (0, 2)


@pytest.mark.parametrize(
    ("instance", "field", "value"),
    [
        (make(), "status", ResearchStatus.RESEARCHED),
        (make_document(), "title", "Other"),
        (make_claim(), "status", ClaimStatus.VERIFIED),
    ],
)
def test_frozen(instance: object, field: str, value: object) -> None:
    with pytest.raises(ValidationError):
        setattr(instance, field, value)


@pytest.mark.parametrize(
    "overrides",
    [
        {"status": "done"},
        {"documents": [{"url": "https://example.com"}]},
        {"claims": [{"text": "X", "evidence_span": "X", "document_indices": []}]},
        {"extra": 1},
    ],
)
def test_invalid_package_rejected(overrides: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        make(**overrides)


@pytest.mark.parametrize(
    "overrides",
    [
        {"url": ""},
        {"title": ""},
        {"source_label": ""},
        {"raw_text_ref": ""},
        {"fetched_at": None},
        {"extra": 1},
    ],
)
def test_invalid_document_rejected(overrides: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        make_document(**overrides)


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
