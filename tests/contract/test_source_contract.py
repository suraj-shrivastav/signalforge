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


RSS_BODY = b"""<?xml version="1.0"?><rss version="2.0"><channel>
<item><title>Post</title><link>https://example.com/post</link>
<pubDate>Sat, 26 Sep 2026 10:00:00 GMT</pubDate></item></channel></rss>"""


ARXIV_BODY = b"""<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom">
<entry><title>Paper</title><link rel="alternate" href="http://arxiv.org/abs/2609.00001v1"/>
<published>2026-09-26T10:00:00Z</published><summary>Abstract.</summary></entry></feed>"""


def _respond(request: httpx.Request) -> httpx.Response:
    if "hn.algolia.com" in request.url.host:
        return httpx.Response(200, json=HN_BODY)
    if request.url.host == "export.arxiv.org":
        return httpx.Response(200, content=ARXIV_BODY)
    return httpx.Response(200, content=RSS_BODY)


def fixture_client() -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(_respond))


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
