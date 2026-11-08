"""Fetch one untrusted page's HTML; every hop must be public and allowed by robots.txt."""

import functools
import ipaddress
import socket
import time
from collections.abc import Callable
from urllib.robotparser import RobotFileParser

import httpx

from signalforge.core.errors import (
    OperationTimeoutError,
    ProviderRejectedError,
    ProviderUnavailableError,
    RateLimitedError,
    SignalForgeError,
)
from signalforge.core.retry import call_with_retry

USER_AGENT = "signalforge/0.1 (+https://github.com/suraj-shrivastav/signalforge)"
REQUEST_TIMEOUT_S = 10.0
MAX_BYTES = 5_000_000
MAX_REDIRECTS = 5
_MAX_RETRY_SLEEP_S = 30.0

_ALLOWED_SCHEMES = frozenset({"http", "https"})
_BLOCKED_SUFFIXES = (".localhost", ".local", ".internal")
_REDIRECT_CODES = frozenset({301, 302, 303, 307, 308})
_DISALLOW_ALL = ["User-agent: *", "Disallow: /"]


def _default_resolve(host: str) -> list[str]:
    return list(dict.fromkeys(str(info[4][0]) for info in socket.getaddrinfo(host, None)))


def _refuse(reason: str) -> ProviderRejectedError:
    # Only a fixed reason: the URL's query string may carry tokens.
    return ProviderRejectedError("URL refused", context={"reason": reason})


def _is_public(address: str) -> bool:
    try:
        return ipaddress.ip_address(address).is_global
    except ValueError:
        return False


class DirectFetcher:
    def __init__(
        self,
        client: httpx.Client,
        *,
        sleep: Callable[[float], None] = time.sleep,
        resolve: Callable[[str], list[str]] = _default_resolve,
    ) -> None:
        self._client = client
        # The page host is untrusted (unlike plugins/sources callers, which only talk to
        # known, trusted source APIs), so a malicious Retry-After can't stall the worker.
        self._sleep = lambda seconds: sleep(min(seconds, _MAX_RETRY_SLEEP_S))
        self._resolve = resolve
        self._robots: dict[str, RobotFileParser] = {}

    def fetch_html(self, url: str, *, max_attempts: int | None = None) -> str:
        """Fetch ``url``; ``max_attempts=1`` makes every request a single try (no retries)."""
        try:
            parsed = httpx.URL(url)
        except httpx.InvalidURL as exc:
            raise _refuse("invalid url") from exc
        return self._follow(parsed, check_robots=True, max_attempts=max_attempts).text

    def _follow(
        self, url: httpx.URL, *, check_robots: bool, max_attempts: int | None = None
    ) -> httpx.Response:
        for _ in range(MAX_REDIRECTS + 1):
            self._guard(url)
            if check_robots and not self._robots_allows(url, max_attempts):
                raise ProviderRejectedError("disallowed by robots.txt", context={"host": url.host})
            response = call_with_retry(
                functools.partial(self._get_once, url),
                sleep=self._sleep,
                **({} if max_attempts is None else {"attempts": max_attempts}),
            )
            if response.status_code not in _REDIRECT_CODES:
                return response
            try:
                url = url.join(response.headers["Location"])
            except httpx.InvalidURL as exc:
                raise _refuse("invalid redirect") from exc
        raise ProviderRejectedError("too many redirects", context={"host": url.host})

    def _guard(self, url: httpx.URL) -> None:
        # Known, accepted limitation: DNS may rebind between this check and connect.
        if url.scheme not in _ALLOWED_SCHEMES:
            raise _refuse("scheme not allowed")
        host = url.host.rstrip(".")
        if not host:
            raise _refuse("missing host")
        if host == "localhost" or host.endswith(_BLOCKED_SUFFIXES):
            raise _refuse("local hostname")
        try:
            ipaddress.ip_address(host)
        except ValueError:
            pass
        else:
            if not _is_public(host):
                raise _refuse("non-public address")
            return
        try:
            addresses = self._resolve(host)
        except OSError as exc:
            raise ProviderUnavailableError("DNS lookup failed", context={"host": host}) from exc
        if not addresses or not all(_is_public(a) for a in addresses):
            raise _refuse("resolves to non-public address")

    def _robots_allows(self, url: httpx.URL, max_attempts: int | None = None) -> bool:
        origin = f"{url.scheme}://{url.netloc.decode('ascii')}"
        parser = self._robots.get(origin)
        if parser is None:
            parser = self._load_robots(httpx.URL(origin + "/robots.txt"), max_attempts)
            self._robots[origin] = parser
        return parser.can_fetch(USER_AGENT, str(url))

    def _load_robots(
        self, robots_url: httpx.URL, max_attempts: int | None = None
    ) -> RobotFileParser:
        parser = RobotFileParser()
        try:
            lines = self._follow(
                robots_url, check_robots=False, max_attempts=max_attempts
            ).text.splitlines()
        except ProviderRejectedError as exc:
            status = exc.context.get("status")
            is_4xx = isinstance(status, int) and httpx.codes.is_client_error(status)
            lines = [] if is_4xx else _DISALLOW_ALL
        except SignalForgeError:
            lines = _DISALLOW_ALL
        parser.parse(lines)
        return parser

    def _get_once(self, url: httpx.URL) -> httpx.Response:
        try:
            response = self._client.get(
                url,
                headers={"User-Agent": USER_AGENT},
                timeout=REQUEST_TIMEOUT_S,
                follow_redirects=False,
            )
        except httpx.TimeoutException as exc:
            raise OperationTimeoutError("page request timed out") from exc
        except (httpx.TransportError, httpx.InvalidURL, httpx.UnsupportedProtocol) as exc:
            raise ProviderUnavailableError("page host is unreachable") from exc
        status = response.status_code
        if status == httpx.codes.TOO_MANY_REQUESTS:
            retry_after = response.headers.get("Retry-After", "")
            raise RateLimitedError(
                "page host rate limited the request",
                retry_after_seconds=float(retry_after)
                if retry_after.isascii() and retry_after.isdigit()
                else None,
            )
        if status >= httpx.codes.INTERNAL_SERVER_ERROR:
            raise ProviderUnavailableError("page host server error", context={"status": status})
        if status >= httpx.codes.BAD_REQUEST:
            raise ProviderRejectedError(
                "page host rejected the request", context={"status": status}
            )
        if status in _REDIRECT_CODES and "Location" in response.headers:
            return response
        if not response.is_success:
            raise ProviderRejectedError("unexpected page status", context={"status": status})
        if len(response.content) > MAX_BYTES:
            raise ProviderRejectedError("page response too large", context={"status": status})
        return response
