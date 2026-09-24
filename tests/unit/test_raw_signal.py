from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from signalforge.core.artifacts.signal import RawSignal

WHEN = datetime(2026, 9, 24, 12, 0, tzinfo=UTC)


def build(**overrides: object) -> RawSignal:
    values: dict[str, object] = {
        "source": "hackernews",
        "source_type": "community",
        "canonical_url": "https://Example.com/a/?utm_source=x",
        "title": "  A title  ",
        "published_at": WHEN,
    }
    return RawSignal(**{**values, **overrides})  # type: ignore[arg-type]


def test_url_is_canonicalised_and_hash_is_filled() -> None:
    signal = build()
    assert signal.canonical_url == "https://example.com/a"
    assert signal.title == "A title"
    assert len(signal.content_hash) == 64


def test_naive_datetime_is_rejected() -> None:
    with pytest.raises(ValidationError):
        build(published_at=datetime(2026, 9, 24, 12, 0))


def test_empty_title_and_unknown_fields_are_rejected() -> None:
    with pytest.raises(ValidationError):
        build(title="   ")
    with pytest.raises(ValidationError):
        build(surprise="x")


def test_same_signal_from_two_runs_has_the_same_digest() -> None:
    assert build().canonical_digest() == build().canonical_digest()
    assert build().canonical_digest() != build(title="Other").canonical_digest()
