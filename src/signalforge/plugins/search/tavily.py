"""Tavily search: secondary-source discovery for the research stage.

The only module that knows Tavily's request and response shape; the rest of the
system sees ``SearchResult`` and the ``SearchProvider`` Protocol.
"""

import time
from collections.abc import Callable

import httpx
from pydantic import BaseModel, ConfigDict, ValidationError

from signalforge.core.errors import (
    ArtifactValidationError,
    OperationTimeoutError,
    ProviderRejectedError,
    ProviderUnavailableError,
    RateLimitedError,
)
from signalforge.core.protocols import SearchResult
from signalforge.core.retry import call_with_retry

SEARCH_URL = "https://api.tavily.com/search"
REQUEST_TIMEOUT_S = 10.0
# Cheapest tier: 1 credit per call ("advanced" costs 2).
SEARCH_DEPTH = "basic"


class _Result(BaseModel):
    # Upstream schema, not ours: ignore keys we do not use instead of failing on them.
    model_config = ConfigDict(extra="ignore")

    url: str
    title: str


class _Response(BaseModel):
    model_config = ConfigDict(extra="ignore")

    results: list[_Result]


class TavilyClient:
    def __init__(
        self,
        client: httpx.Client,
        *,
        api_key: str,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._client = client
        self._api_key = api_key
        self._sleep = sleep

    def search(self, query: str, *, max_results: int = 3) -> list[SearchResult]:
        payload: dict[str, str | int] = {
            "query": query,
            "max_results": max_results,
            "search_depth": SEARCH_DEPTH,
        }
        results = call_with_retry(lambda: self._post(payload), sleep=self._sleep)
        return [SearchResult(url=r.url, title=r.title) for r in results[:max_results]]

    def _post(self, payload: dict[str, str | int]) -> list[_Result]:
        # Every message and context below is fixed text or a status code, so the
        # key (sent only in the header) can never leak into an error.
        try:
            response = self._client.post(
                SEARCH_URL,
                json=payload,
                headers={"Authorization": f"Bearer {self._api_key}"},
                timeout=REQUEST_TIMEOUT_S,
            )
        except httpx.TimeoutException as exc:
            raise OperationTimeoutError("Tavily request timed out") from exc
        except (httpx.TransportError, httpx.InvalidURL, httpx.UnsupportedProtocol) as exc:
            raise ProviderUnavailableError("Tavily is unreachable") from exc

        status = response.status_code
        if status == httpx.codes.TOO_MANY_REQUESTS:
            retry_after = response.headers.get("Retry-After", "")
            raise RateLimitedError(
                "Tavily rate limited the request",
                retry_after_seconds=float(retry_after)
                if retry_after.isascii() and retry_after.isdigit()
                else None,
            )
        if status >= httpx.codes.INTERNAL_SERVER_ERROR:
            raise ProviderUnavailableError("Tavily server error", context={"status": status})
        if status >= httpx.codes.BAD_REQUEST:
            raise ProviderRejectedError("Tavily rejected the request", context={"status": status})
        try:
            return _Response.model_validate_json(response.content).results
        except ValidationError as exc:
            raise ArtifactValidationError(
                "Unexpected Tavily response shape", context={"errors": exc.error_count()}
            ) from exc
