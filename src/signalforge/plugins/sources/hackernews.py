"""Hacker News via the public Algolia search API. No key required.

The only module that knows this API's shape; the rest of the system sees
``RawSignal`` and the ``Source`` Protocol.
"""

import logging
import time
from collections.abc import Callable, Sequence
from datetime import UTC, datetime

import httpx
from pydantic import BaseModel, ConfigDict, ValidationError

from signalforge.core.artifacts.signal import RawSignal
from signalforge.core.errors import (
    ArtifactValidationError,
    OperationTimeoutError,
    ProviderRejectedError,
    ProviderUnavailableError,
    RateLimitedError,
)
from signalforge.core.retry import call_with_retry

log = logging.getLogger(__name__)

SEARCH_URL = "https://hn.algolia.com/api/v1/search_by_date"
REQUEST_TIMEOUT_S = 10.0
# ponytail: hard-coded until the vertical config (ai_engineering.yaml) exists.
DEFAULT_QUERIES: tuple[str, ...] = ("LLM", "AI agent", "RAG", "fine-tuning", "inference")


class _Hit(BaseModel):
    # Upstream schema, not ours: ignore keys we do not use instead of failing on them.
    model_config = ConfigDict(extra="ignore")

    objectID: str  # noqa: N815  (upstream field name)
    title: str
    url: str | None = None
    created_at_i: int
    points: int | None = None
    num_comments: int | None = None
    author: str | None = None


class _Response(BaseModel):
    model_config = ConfigDict(extra="ignore")

    hits: list[_Hit]


class HackerNewsSource:
    name = "hackernews"
    source_type = "community"

    def __init__(
        self,
        client: httpx.Client,
        *,
        queries: Sequence[str] = DEFAULT_QUERIES,
        min_points: int = 20,
        per_query: int = 50,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._client = client
        self._queries = tuple(queries)
        self._min_points = min_points
        self._per_query = per_query
        self._sleep = sleep

    def fetch(self, since: datetime) -> list[RawSignal]:
        signals: dict[str, RawSignal] = {}
        for query in self._queries:
            for hit in self._search(query, since):
                signal = self._to_signal(hit)
                if signal is not None:
                    signals.setdefault(signal.canonical_url, signal)
        return list(signals.values())

    def _search(self, query: str, since: datetime) -> list[_Hit]:
        params: dict[str, str | int] = {
            "tags": "story",
            "query": query,
            "numericFilters": f"created_at_i>{int(since.timestamp())},points>={self._min_points}",
            "hitsPerPage": self._per_query,
        }
        return call_with_retry(lambda: self._get(params), sleep=self._sleep)

    def _get(self, params: dict[str, str | int]) -> list[_Hit]:
        try:
            response = self._client.get(SEARCH_URL, params=params, timeout=REQUEST_TIMEOUT_S)
        except httpx.TimeoutException as exc:
            raise OperationTimeoutError("Hacker News request timed out") from exc
        except httpx.TransportError as exc:
            raise ProviderUnavailableError("Hacker News is unreachable") from exc

        status = response.status_code
        if status == httpx.codes.TOO_MANY_REQUESTS:
            retry_after = response.headers.get("Retry-After", "")
            raise RateLimitedError(
                "Hacker News rate limited the request",
                retry_after_seconds=float(retry_after) if retry_after.isdigit() else None,
            )
        if status >= httpx.codes.INTERNAL_SERVER_ERROR:
            raise ProviderUnavailableError("Hacker News server error", context={"status": status})
        if status >= httpx.codes.BAD_REQUEST:
            raise ProviderRejectedError(
                "Hacker News rejected the request", context={"status": status}
            )
        try:
            return _Response.model_validate_json(response.content).hits
        except ValidationError as exc:
            raise ArtifactValidationError(
                "Unexpected Hacker News response shape", context={"errors": exc.error_count()}
            ) from exc

    def _to_signal(self, hit: _Hit) -> RawSignal | None:
        if not hit.url:  # Ask HN and similar posts have no external page to research.
            return None
        try:
            return RawSignal(
                source=self.name,
                source_type=self.source_type,
                canonical_url=hit.url,
                title=hit.title,
                published_at=datetime.fromtimestamp(hit.created_at_i, UTC),
                metadata={
                    "hn_id": hit.objectID,
                    "hn_url": f"https://news.ycombinator.com/item?id={hit.objectID}",
                    "points": hit.points,
                    "num_comments": hit.num_comments,
                    "author": hit.author,
                },
            )
        except (ArtifactValidationError, ValueError) as exc:
            # One malformed item must not fail the whole run, but it must not vanish silently.
            log.warning("skipping hit", extra={"hn_id": hit.objectID, "error": str(exc)})
            return None
