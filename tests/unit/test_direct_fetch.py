import socket
from collections.abc import Callable

import httpx
import pytest

from signalforge.core.errors import (
    OperationTimeoutError,
    ProviderRejectedError,
    ProviderUnavailableError,
)
from signalforge.plugins.search import direct_fetch
from signalforge.plugins.search.direct_fetch import (
    MAX_BYTES,
    MAX_REDIRECTS,
    USER_AGENT,
    DirectFetcher,
)

Handler = Callable[[httpx.Request], httpx.Response]
PUBLIC = ["93.184.216.34"]
HTML = "<html><body>hello</body></html>"


def serve(page: Handler, robots: Handler = lambda _: httpx.Response(404)) -> Handler:
    return lambda request: robots(request) if request.url.path == "/robots.txt" else page(request)


def fetcher(
    handler: Handler,
    *,
    resolve: Callable[[str], list[str]] = lambda _: PUBLIC,
    sleep: Callable[[float], None] = lambda _: None,
) -> tuple[DirectFetcher, list[httpx.Request]]:
    seen: list[httpx.Request] = []

    def record(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return handler(request)

    client = httpx.Client(transport=httpx.MockTransport(record))
    return DirectFetcher(client, sleep=sleep, resolve=resolve), seen


def pages(seen: list[httpx.Request]) -> list[str]:
    return [str(r.url) for r in seen if r.url.path != "/robots.txt"]


def test_returns_the_html_and_sends_the_user_agent_when_robots_is_a_404() -> None:
    fetch, seen = fetcher(serve(lambda _: httpx.Response(200, text=HTML)))  # robots.txt 404
    assert fetch.fetch_html("https://example.com/post") == HTML
    assert [str(r.url) for r in seen] == [
        "https://example.com/robots.txt",
        "https://example.com/post",
    ]
    assert all(r.headers["User-Agent"] == USER_AGENT for r in seen)


@pytest.mark.parametrize(
    ("url", "resolved"),
    [
        ("ftp://example.com/x", PUBLIC),
        ("file:///etc/passwd", PUBLIC),
        ("http:///no-host", PUBLIC),
        ("http://localhost/", PUBLIC),
        ("http://api.localhost/", PUBLIC),
        ("http://printer.local/", PUBLIC),
        ("http://metadata.google.internal/", PUBLIC),
        ("http://127.0.0.1/", PUBLIC),
        ("http://10.0.0.1/", PUBLIC),
        ("http://169.254.169.254/latest/meta-data", PUBLIC),
        ("http://[::1]:8080/", PUBLIC),
        ("https://sneaky.example.com/", ["93.184.216.34", "192.168.1.5"]),
    ],
)
def test_unsafe_urls_are_refused_before_any_request(url: str, resolved: list[str]) -> None:
    fetch, seen = fetcher(
        serve(lambda _: httpx.Response(200, text=HTML)), resolve=lambda _: resolved
    )
    with pytest.raises(ProviderRejectedError) as caught:
        fetch.fetch_html(url + "?token=secret")
    assert seen == []
    assert "reason" in caught.value.context
    assert "secret" not in str(caught.value)


def test_a_dns_failure_is_unavailable_not_a_refusal() -> None:
    def fail(_: str) -> list[str]:
        raise socket.gaierror("no such host")

    fetch, seen = fetcher(serve(lambda _: httpx.Response(200, text=HTML)), resolve=fail)
    with pytest.raises(ProviderUnavailableError):
        fetch.fetch_html("https://example.com/")
    assert seen == []


def test_a_redirect_to_a_private_host_is_refused() -> None:
    def page(_: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"Location": "http://intranet.example.com/"})

    def resolve(host: str) -> list[str]:
        return ["10.1.2.3"] if host == "intranet.example.com" else PUBLIC

    fetch, seen = fetcher(serve(page), resolve=resolve)
    with pytest.raises(ProviderRejectedError):
        fetch.fetch_html("https://example.com/start")
    assert all(r.url.host == "example.com" for r in seen)


def test_a_redirect_chain_to_a_public_host_is_followed() -> None:
    def page(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/a":
            return httpx.Response(301, headers={"Location": "/b"})
        if request.url.path == "/b":
            return httpx.Response(302, headers={"Location": "https://other.example.org/c"})
        return httpx.Response(200, text=HTML)

    fetch, seen = fetcher(serve(page))
    assert fetch.fetch_html("https://example.com/a") == HTML
    assert pages(seen) == [
        "https://example.com/a",
        "https://example.com/b",
        "https://other.example.org/c",
    ]
    robots_hosts = [r.url.host for r in seen if r.url.path == "/robots.txt"]
    assert robots_hosts == ["example.com", "other.example.org"]


def test_too_many_redirects_is_rejected() -> None:
    def page(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"Location": request.url.path + "x"})

    fetch, seen = fetcher(serve(page))
    with pytest.raises(ProviderRejectedError):
        fetch.fetch_html("https://example.com/x")
    assert len(pages(seen)) == MAX_REDIRECTS + 1


@pytest.mark.parametrize(
    "rules",
    ["User-agent: *\nDisallow: /private", "User-agent: signalforge\nDisallow: /"],
)
def test_a_path_disallowed_by_robots_is_rejected(rules: str) -> None:
    fetch, seen = fetcher(
        serve(lambda _: httpx.Response(200, text=HTML), lambda _: httpx.Response(200, text=rules))
    )
    with pytest.raises(ProviderRejectedError, match="robots"):
        fetch.fetch_html("https://example.com/private/page")
    assert pages(seen) == []


def _raise_timeout(request: httpx.Request) -> httpx.Response:
    raise httpx.ReadTimeout("slow", request=request)


@pytest.mark.parametrize("robots", [lambda _: httpx.Response(503), _raise_timeout])
def test_an_unavailable_robots_file_disallows_the_host(robots: Handler) -> None:
    fetch, seen = fetcher(serve(lambda _: httpx.Response(200, text=HTML), robots))
    with pytest.raises(ProviderRejectedError, match="robots"):
        fetch.fetch_html("https://example.com/page")
    assert pages(seen) == []


def test_robots_is_fetched_once_per_host() -> None:
    fetch, seen = fetcher(serve(lambda _: httpx.Response(200, text=HTML)))
    fetch.fetch_html("https://example.com/one")
    fetch.fetch_html("https://example.com/two")
    assert sum(r.url.path == "/robots.txt" for r in seen) == 1


def test_a_503_is_retried_then_succeeds() -> None:
    statuses = iter([503, 200])
    fetch, seen = fetcher(serve(lambda _: httpx.Response(next(statuses), text=HTML)))
    assert fetch.fetch_html("https://example.com/") == HTML
    assert len(pages(seen)) == 2


def test_a_404_is_permanent_and_not_retried() -> None:
    fetch, seen = fetcher(serve(lambda _: httpx.Response(404)))
    with pytest.raises(ProviderRejectedError) as caught:
        fetch.fetch_html("https://example.com/gone")
    assert caught.value.context["status"] == 404
    assert len(pages(seen)) == 1


def test_429_honours_retry_after() -> None:
    responses = iter(
        [httpx.Response(429, headers={"Retry-After": "7"}), httpx.Response(200, text=HTML)]
    )
    sleeps: list[float] = []
    fetch, _ = fetcher(serve(lambda _: next(responses)), sleep=sleeps.append)
    assert fetch.fetch_html("https://example.com/") == HTML
    assert sleeps == [7.0]


def test_429_retry_after_sleep_is_capped() -> None:
    responses = iter(
        [
            httpx.Response(429, headers={"Retry-After": "999999999"}),
            httpx.Response(200, text=HTML),
        ]
    )
    sleeps: list[float] = []
    fetch, _ = fetcher(serve(lambda _: next(responses)), sleep=sleeps.append)
    assert fetch.fetch_html("https://example.com/") == HTML
    assert sleeps == [30.0]


def test_a_page_timeout_maps_to_operation_timeout() -> None:
    fetch, _ = fetcher(serve(_raise_timeout))
    with pytest.raises(OperationTimeoutError):
        fetch.fetch_html("https://example.com/")


def test_an_oversize_body_is_rejected() -> None:
    fetch, _ = fetcher(serve(lambda _: httpx.Response(200, content=b"x" * (MAX_BYTES + 1))))
    with pytest.raises(ProviderRejectedError, match="too large"):
        fetch.fetch_html("https://example.com/")


def test_default_resolve_returns_unique_addresses(monkeypatch: pytest.MonkeyPatch) -> None:
    info = (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))
    monkeypatch.setattr(socket, "getaddrinfo", lambda *_: [info, info])
    assert direct_fetch._default_resolve("example.com") == ["93.184.216.34"]
