import json
from collections.abc import Callable

import httpx
import pytest

from signalforge.core.errors import (
    OperationTimeoutError,
    ProviderRejectedError,
    ProviderUnavailableError,
    RateLimitedError,
    SignalForgeError,
)
from signalforge.plugins.search.tavily import SEARCH_DEPTH, SEARCH_URL, TavilyClient

KEY = "test-key"

Handler = Callable[[httpx.Request], httpx.Response]


def body(n: int) -> dict[str, object]:
    return {
        "query": "q",
        "results": [
            {"url": f"https://{i}.example.com", "title": f"T{i}", "content": "x", "score": 0.5}
            for i in range(n)
        ],
    }


def tavily(handler: Handler, sleep: Callable[[float], None] = lambda _: None) -> TavilyClient:
    return TavilyClient(
        httpx.Client(transport=httpx.MockTransport(handler)), api_key=KEY, sleep=sleep
    )


def test_caps_results_at_max_results() -> None:
    results = tavily(lambda _: httpx.Response(200, json=body(4))).search("q", max_results=3)
    assert [r.url for r in results] == [f"https://{i}.example.com" for i in range(3)]
    assert results[0].title == "T0"


def test_sends_bearer_auth_and_keeps_the_key_out_of_the_body() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=body(1))

    tavily(handler).search("model X release", max_results=2)
    [request] = seen
    assert request.method == "POST"
    assert str(request.url) == SEARCH_URL
    assert request.headers["Authorization"] == f"Bearer {KEY}"
    sent = json.loads(request.content)
    assert sent == {"query": "model X release", "max_results": 2, "search_depth": SEARCH_DEPTH}
    assert "api_key" not in sent
    assert KEY not in request.content.decode()


def test_retries_a_503_then_succeeds() -> None:
    calls = {"n": 0}

    def handler(_: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(503)
        return httpx.Response(200, json=body(1))

    assert len(tavily(handler).search("q")) == 1
    assert calls["n"] == 2


def test_a_400_is_permanent_and_not_retried() -> None:
    calls = {"n": 0}

    def handler(_: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(400)

    with pytest.raises(ProviderRejectedError):
        tavily(handler).search("q")
    assert calls["n"] == 1


def test_429_is_retried_and_retry_after_is_honoured() -> None:
    calls = {"n": 0}
    sleeps: list[float] = []

    def handler(_: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(429, headers={"Retry-After": "7"})
        return httpx.Response(200, json=body(1))

    assert len(tavily(handler, sleep=sleeps.append).search("q")) == 1
    assert sleeps == [7.0]


def test_timeout_maps_to_operation_timeout() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    with pytest.raises(OperationTimeoutError):
        tavily(handler).search("q")


@pytest.mark.parametrize(
    "payload",
    [b"not json", b'{"nope": []}', b'{"results": [{"url": 1}]}'],
    ids=["not-json", "no-results-key", "bad-result"],
)
def test_malformed_body_is_rejected_and_not_retried(payload: bytes) -> None:
    calls = {"n": 0}

    def handler(_: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(200, content=payload)

    with pytest.raises(ProviderRejectedError):
        tavily(handler).search("q")
    assert calls["n"] == 1


def _raise_connect(request: httpx.Request) -> httpx.Response:
    raise httpx.ConnectError("refused", request=request)


def _raise_timeout(request: httpx.Request) -> httpx.Response:
    raise httpx.ReadTimeout("slow", request=request)


@pytest.mark.parametrize(
    ("handler", "expected"),
    [
        (lambda _: httpx.Response(401), ProviderRejectedError),
        (lambda _: httpx.Response(429), RateLimitedError),
        (lambda _: httpx.Response(503), ProviderUnavailableError),
        (lambda _: httpx.Response(200, content=b"<html>"), ProviderRejectedError),
        (_raise_connect, ProviderUnavailableError),
        (_raise_timeout, OperationTimeoutError),
    ],
    ids=["401", "429", "503", "malformed", "connect", "timeout"],
)
def test_errors_are_typed_and_never_contain_the_key(
    handler: Handler, expected: type[SignalForgeError]
) -> None:
    with pytest.raises(expected) as caught:
        tavily(handler).search("q")
    assert KEY not in str(caught.value)
    assert KEY not in repr(caught.value.context)
