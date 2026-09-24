"""Every Source must satisfy the Protocol and emit well-formed signals (standards §4)."""

from datetime import UTC, datetime

import httpx
import pytest

from signalforge.core.protocols import Source
from signalforge.plugins.sources import SOURCE_NAMES, build_source

HN_BODY = {
    "hits": [
        {
            "objectID": "1",
            "title": "Story",
            "url": "https://example.com/story",
            "created_at_i": 1790223659,
            "points": 40,
            "num_comments": 3,
            "author": "a",
        }
    ]
}


def fixture_client() -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(200, json=HN_BODY)))


@pytest.mark.parametrize("name", SOURCE_NAMES)
def test_source_satisfies_the_protocol_and_emits_valid_signals(name: str) -> None:
    source = build_source(name, fixture_client())
    assert isinstance(source, Source)
    assert source.name == name
    signals = list(source.fetch(datetime(2026, 9, 1, tzinfo=UTC)))
    assert signals
    for signal in signals:
        assert signal.source == name
        assert signal.published_at.tzinfo is not None
        assert signal.canonical_url == signal.canonical_url.rstrip("/")


def test_unknown_source_name_is_a_key_error() -> None:
    with pytest.raises(KeyError):
        build_source("nope", fixture_client())
