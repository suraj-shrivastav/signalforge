"""Canonicalisation is the dedupe key (PRD §12), so equivalent URLs must collapse."""

import pytest

from signalforge.core.canonical import canonical_url, content_hash
from signalforge.core.errors import ArtifactValidationError


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("HTTPS://Example.COM/Post/", "https://example.com/Post"),
        ("https://example.com/a#section", "https://example.com/a"),
        ("https://example.com:443/a", "https://example.com/a"),
        ("http://example.com:80/a", "http://example.com/a"),
        ("https://example.com:8443/a", "https://example.com:8443/a"),
        ("https://example.com/a?utm_source=x&b=2&a=1&fbclid=z", "https://example.com/a?a=1&b=2"),
        ("https://user:pw@example.com/a", "https://example.com/a"),
        ("https://example.com", "https://example.com"),
        ("  https://example.com/a  ", "https://example.com/a"),
    ],
)
def test_canonical_url_collapses_equivalent_forms(raw: str, expected: str) -> None:
    assert canonical_url(raw) == expected


@pytest.mark.parametrize(
    "bad", ["", "not a url", "ftp://example.com/a", "https://", "javascript:alert(1)"]
)
def test_canonical_url_rejects_non_http_urls(bad: str) -> None:
    with pytest.raises(ArtifactValidationError):
        canonical_url(bad)


def test_canonical_url_is_idempotent() -> None:
    once = canonical_url("https://Example.com/a/?utm_medium=x&z=1#f")
    assert canonical_url(once) == once


def test_content_hash_ignores_case_and_whitespace_but_not_meaning() -> None:
    assert content_hash("Hello  World", "a b") == content_hash(" hello world ", "A\nB")
    assert content_hash("Hello", "a") != content_hash("Hello", "b")
    assert len(content_hash("t", "s")) == 64
