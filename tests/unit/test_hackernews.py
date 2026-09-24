from datetime import UTC, datetime

import httpx
import pytest

from signalforge.core.errors import (
    ArtifactValidationError,
    OperationTimeoutError,
    ProviderRejectedError,
    ProviderUnavailableError,
)
from signalforge.plugins.sources._http import USER_AGENT
from signalforge.plugins.sources.hackernews import HackerNewsSource

SINCE = datetime(2026, 9, 23, tzinfo=UTC)


def hit(
    n: int, *, url: str | None = "https://example.com/{n}", **extra: object
) -> dict[str, object]:
    return {
        "objectID": str(n),
        "title": f"Story {n}",
        "url": url.format(n=n) if url else None,
        "created_at_i": 1790223659 + n,
        "points": 50,
        "num_comments": 7,
        "author": "someone",
        **extra,
    }


def source(handler: httpx.MockTransport | None = None, **kwargs: object) -> HackerNewsSource:
    client = httpx.Client(
        transport=handler or httpx.MockTransport(lambda _: httpx.Response(200, json={"hits": []}))
    )
    return HackerNewsSource(client, sleep=lambda _: None, **kwargs)  # type: ignore[arg-type]


def test_maps_hits_to_raw_signals() -> None:
    transport = httpx.MockTransport(lambda _: httpx.Response(200, json={"hits": [hit(1)]}))
    [signal] = source(transport, queries=["LLM"]).fetch(SINCE)
    assert signal.source == "hackernews"
    assert signal.canonical_url == "https://example.com/1"
    assert signal.published_at.tzinfo is not None
    assert signal.metadata["hn_id"] == "1"
    assert signal.metadata["points"] == 50


def test_sends_the_time_and_points_filters() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"hits": []})

    source(httpx.MockTransport(handler), queries=["LLM"], min_points=30).fetch(SINCE)
    params = seen[0].url.params
    assert params["query"] == "LLM"
    assert params["tags"] == "story"
    assert f"created_at_i>{int(SINCE.timestamp())}" in params["numericFilters"]
    assert "points>=30" in params["numericFilters"]


def test_skips_stories_without_a_url_and_dedupes_across_queries() -> None:
    transport = httpx.MockTransport(
        lambda _: httpx.Response(200, json={"hits": [hit(1), hit(2, url=None)]})
    )
    signals = list(source(transport, queries=["LLM", "RAG"]).fetch(SINCE))
    assert [s.canonical_url for s in signals] == ["https://example.com/1"]


def test_a_bad_url_skips_that_hit_only() -> None:
    transport = httpx.MockTransport(
        lambda _: httpx.Response(200, json={"hits": [hit(1, url="ftp://x/y"), hit(2)]})
    )
    signals = list(source(transport, queries=["LLM"]).fetch(SINCE))
    assert [s.title for s in signals] == ["Story 2"]


def test_retries_a_503_then_succeeds() -> None:
    calls = {"n": 0}

    def handler(_: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(503)
        return httpx.Response(200, json={"hits": [hit(1)]})

    assert len(list(source(httpx.MockTransport(handler), queries=["LLM"]).fetch(SINCE))) == 1
    assert calls["n"] == 2


def test_a_400_is_permanent_and_not_retried() -> None:
    calls = {"n": 0}

    def handler(_: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(400)

    with pytest.raises(ProviderRejectedError):
        source(httpx.MockTransport(handler), queries=["LLM"]).fetch(SINCE)
    assert calls["n"] == 1


def test_persistent_503_raises_provider_unavailable() -> None:
    transport = httpx.MockTransport(lambda _: httpx.Response(503))
    with pytest.raises(ProviderUnavailableError):
        source(transport, queries=["LLM"]).fetch(SINCE)


def test_timeout_maps_to_operation_timeout() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    with pytest.raises(OperationTimeoutError):
        source(httpx.MockTransport(handler), queries=["LLM"]).fetch(SINCE)


def test_malformed_payload_is_a_validation_error() -> None:
    transport = httpx.MockTransport(lambda _: httpx.Response(200, json={"hits": [{"objectID": 1}]}))
    with pytest.raises(ArtifactValidationError):
        source(transport, queries=["LLM"]).fetch(SINCE)


def test_sends_the_user_agent_header() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"hits": []})

    source(httpx.MockTransport(handler), queries=["LLM"]).fetch(SINCE)
    assert seen[0].headers["User-Agent"] == USER_AGENT


def test_429_is_retried_and_retry_after_is_honoured() -> None:
    calls = {"n": 0}
    sleeps: list[float] = []

    def handler(_: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(429, headers={"Retry-After": "7"})
        return httpx.Response(200, json={"hits": [hit(1)]})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    signals = HackerNewsSource(client, queries=["LLM"], sleep=sleeps.append).fetch(SINCE)
    assert len(signals) == 1
    assert sleeps == [7.0]


def test_absurd_timestamp_skips_the_hit() -> None:
    body = {"hits": [hit(1, created_at_i=10**18), hit(2)]}
    transport = httpx.MockTransport(lambda _: httpx.Response(200, json=body))
    assert [s.title for s in source(transport, queries=["LLM"]).fetch(SINCE)] == ["Story 2"]
