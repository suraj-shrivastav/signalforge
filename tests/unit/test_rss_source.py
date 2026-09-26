from collections.abc import Callable
from datetime import UTC, datetime

import httpx
import pytest

from signalforge.core.errors import ProviderUnavailableError
from signalforge.plugins.sources.rss import RssSource

FEED = b"""<?xml version="1.0"?><rss version="2.0"><channel>
<item><title>New</title><link>https://a.example/new?utm_source=x</link>
<pubDate>Sat, 26 Sep 2026 10:00:00 GMT</pubDate><description>Fresh</description></item>
<item><title>Old</title><link>https://a.example/old</link>
<pubDate>Mon, 01 Jan 2024 10:00:00 GMT</pubDate></item>
<item><title>Undated</title><link>https://a.example/undated</link></item>
</channel></rss>"""
SINCE = datetime(2026, 9, 25, tzinfo=UTC)


def _client(handler: Callable[[httpx.Request], httpx.Response]) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def _no_sleep(_: float) -> None:
    return None


def test_returns_only_entries_since_and_canonicalises() -> None:
    src = RssSource(
        _client(lambda _: httpx.Response(200, content=FEED)), feeds=("https://f.example/rss",)
    )
    [signal] = src.fetch(SINCE)
    assert signal.title == "New"
    assert signal.canonical_url == "https://a.example/new"
    assert signal.source == "rss"
    assert signal.metadata["feed"] == "https://f.example/rss"


def test_one_bad_feed_does_not_stop_others() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return (
            httpx.Response(404) if "bad" in str(request.url) else httpx.Response(200, content=FEED)
        )

    src = RssSource(
        _client(handler),
        feeds=("https://bad.example/rss", "https://ok.example/rss"),
        sleep=_no_sleep,
    )
    assert len(src.fetch(SINCE)) == 1


def test_malformed_feed_is_skipped_not_fatal() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        content = b"<not xml" if "bad" in str(request.url) else FEED
        return httpx.Response(200, content=content)

    src = RssSource(
        _client(handler),
        feeds=("https://bad.example/rss", "https://ok.example/rss"),
        sleep=_no_sleep,
    )
    assert len(src.fetch(SINCE)) == 1


def test_all_feeds_failing_raises() -> None:
    src = RssSource(
        _client(lambda _: httpx.Response(404)), feeds=("https://bad.example/rss",), sleep=_no_sleep
    )
    with pytest.raises(ProviderUnavailableError):
        src.fetch(SINCE)
