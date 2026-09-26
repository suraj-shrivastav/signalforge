"""Shared HTTP constants and fetch helper for source plugins."""

import time
from collections.abc import Callable

import httpx

from signalforge.core.errors import (
    OperationTimeoutError,
    ProviderRejectedError,
    ProviderUnavailableError,
    RateLimitedError,
)
from signalforge.core.retry import call_with_retry

USER_AGENT = "signalforge/0.1 (+https://github.com/suraj-shrivastav/signalforge)"
REQUEST_TIMEOUT_S = 10.0
MAX_BYTES = 5_000_000


def fetch_bytes(
    client: httpx.Client,
    url: str,
    *,
    label: str,
    params: dict[str, str | int] | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> bytes:
    """GET ``url`` with retries; every failure is mapped to a SignalForgeError subtype."""

    def once() -> bytes:
        try:
            response = client.get(
                url, params=params, headers={"User-Agent": USER_AGENT}, timeout=REQUEST_TIMEOUT_S
            )
        except httpx.TimeoutException as exc:
            raise OperationTimeoutError(f"{label} request timed out") from exc
        except (httpx.TransportError, httpx.InvalidURL, httpx.UnsupportedProtocol) as exc:
            raise ProviderUnavailableError(f"{label} is unreachable") from exc
        status = response.status_code
        if status == httpx.codes.TOO_MANY_REQUESTS:
            retry_after = response.headers.get("Retry-After", "")
            raise RateLimitedError(
                f"{label} rate limited the request",
                retry_after_seconds=float(retry_after)
                if retry_after.isascii() and retry_after.isdigit()
                else None,
            )
        if status >= httpx.codes.INTERNAL_SERVER_ERROR:
            raise ProviderUnavailableError(f"{label} server error", context={"status": status})
        if status >= httpx.codes.BAD_REQUEST:
            raise ProviderRejectedError(f"{label} rejected the request", context={"status": status})
        if len(response.content) > MAX_BYTES:
            raise ProviderRejectedError(f"{label} response too large", context={"status": status})
        return response.content

    return call_with_retry(once, sleep=sleep)
