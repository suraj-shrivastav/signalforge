from datetime import UTC, datetime

import httpx
import pytest

from signalforge.core.errors import (
    ArtifactValidationError,
    OperationTimeoutError,
    ProviderRejectedError,
    ProviderUnavailableError,
    RateLimitedError,
)
from signalforge.plugins.sources._http import fetch_bytes
from signalforge.plugins.sources.feeds import parse_feed

RSS = b"""<?xml version="1.0"?><rss version="2.0"><channel>
<item><title>Model X</title><link>https://a.example/x</link>
<pubDate>Sat, 26 Sep 2026 10:00:00 GMT</pubDate><description>Big &amp; new</description></item>
<item><title>No link</title></item>
<item><link>https://a.example/notitle</link></item>
</channel></rss>"""

ATOM = b"""<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom">
<entry><title>Paper Y</title><link rel="alternate" href="https://b.example/y"/>
<published>2026-09-26T10:00:00Z</published><summary>Abstract</summary></entry></feed>"""


def test_parses_rss() -> None:
    [entry] = parse_feed(RSS)
    assert entry.title == "Model X"
    assert entry.link == "https://a.example/x"
    assert entry.published == datetime(2026, 9, 26, 10, tzinfo=UTC)
    assert entry.summary == "Big & new"


def test_parses_atom() -> None:
    [entry] = parse_feed(ATOM)
    assert (entry.title, entry.link) == ("Paper Y", "https://b.example/y")
    assert entry.published == datetime(2026, 9, 26, 10, tzinfo=UTC)


@pytest.mark.parametrize("body", [b"<rss><oops", b"", b"not xml at all", b"{}"])
def test_rejects_malformed_or_non_xml(body: bytes) -> None:
    with pytest.raises(ArtifactValidationError):
        parse_feed(body)


def test_bad_date_becomes_none() -> None:
    xml = (
        b"<rss><channel><item><title>T</title><link>https://a.example/t</link>"
        b"<pubDate>garbage</pubDate></item>"
        b"<item><title>U</title><link>https://a.example/u</link>"
        b"<pubDate>2026-13-45T00:00:00Z</pubDate></item></channel></rss>"
    )
    entries = parse_feed(xml)
    assert [e.published for e in entries] == [None, None]


def test_empty_feed() -> None:
    assert parse_feed(b"<rss><channel></channel></rss>") == []
    assert parse_feed(b'<feed xmlns="http://www.w3.org/2005/Atom"/>') == []


def _client(handler: httpx.MockTransport) -> httpx.Client:
    return httpx.Client(transport=handler)


def _no_sleep(_: float) -> None:
    return None


def test_fetch_returns_body() -> None:
    client = _client(httpx.MockTransport(lambda _r: httpx.Response(200, content=b"ok")))
    assert fetch_bytes(client, "https://x.example/", label="X", sleep=_no_sleep) == b"ok"


def test_fetch_5xx_retries_then_unavailable() -> None:
    calls = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(503)

    with pytest.raises(ProviderUnavailableError):
        fetch_bytes(
            _client(httpx.MockTransport(handler)), "https://x.example/", label="X", sleep=_no_sleep
        )
    assert calls > 1


def test_fetch_4xx_rejected_without_retry() -> None:
    calls = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(404)

    with pytest.raises(ProviderRejectedError):
        fetch_bytes(
            _client(httpx.MockTransport(handler)), "https://x.example/", label="X", sleep=_no_sleep
        )
    assert calls == 1


@pytest.mark.parametrize(
    ("header", "expected"), [("7", 7.0), ("Wed, 21 Oct 2026 07:28:00 GMT", None)]
)
def test_fetch_429_retry_after(header: str, expected: float | None) -> None:
    transport = httpx.MockTransport(lambda _r: httpx.Response(429, headers={"Retry-After": header}))
    seen: list[RateLimitedError] = []

    def sleep(_: float) -> None:
        return None

    try:
        fetch_bytes(_client(transport), "https://x.example/", label="X", sleep=sleep)
    except RateLimitedError as exc:
        seen.append(exc)
    assert len(seen) == 1
    assert seen[0].retry_after_seconds == expected


def test_fetch_timeout_maps() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow")

    with pytest.raises(OperationTimeoutError):
        fetch_bytes(
            _client(httpx.MockTransport(handler)), "https://x.example/", label="X", sleep=_no_sleep
        )


def test_fetch_transport_error_maps() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down")

    with pytest.raises(ProviderUnavailableError):
        fetch_bytes(
            _client(httpx.MockTransport(handler)), "https://x.example/", label="X", sleep=_no_sleep
        )
