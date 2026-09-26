"""arXiv source: newest papers in the configured categories via the Atom API."""

import logging
import re
import time
from collections.abc import Callable, Sequence
from datetime import datetime

import httpx
from pydantic import ValidationError

from signalforge.core.artifacts.signal import RawSignal
from signalforge.plugins.sources._http import fetch_bytes
from signalforge.plugins.sources.feeds import parse_feed

log = logging.getLogger(__name__)

API_URL = "https://export.arxiv.org/api/query"
_VERSION_SUFFIX = re.compile(r"v\d+$")


class ArxivSource:
    name = "arxiv"
    source_type = "paper"

    def __init__(
        self,
        client: httpx.Client,
        *,
        categories: Sequence[str] = ("cs.AI", "cs.CL", "cs.LG"),
        max_results: int = 100,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._client = client
        self._categories = tuple(categories)
        self._max_results = max_results
        self._sleep = sleep

    def fetch(self, since: datetime) -> list[RawSignal]:
        # One request per run, so arXiv's 3s throttle does not apply.
        body = fetch_bytes(
            self._client,
            API_URL,
            label="arXiv",
            params={
                "search_query": " OR ".join(f"cat:{c}" for c in self._categories),
                "sortBy": "submittedDate",
                "sortOrder": "descending",
                "max_results": self._max_results,
            },
            sleep=self._sleep,
        )
        signals: dict[str, RawSignal] = {}
        for entry in parse_feed(body):
            if entry.published is None or entry.published <= since:
                continue
            try:
                signal = RawSignal(
                    source=self.name,
                    source_type=self.source_type,
                    canonical_url=_VERSION_SUFFIX.sub("", entry.link.strip()),
                    title=" ".join(entry.title.split()),
                    summary=" ".join(entry.summary.split()) if entry.summary else entry.summary,
                    published_at=entry.published,
                    metadata={},
                )
            except ValidationError:
                log.warning("skipping malformed arXiv entry", extra={"link": entry.link})
                continue
            signals.setdefault(signal.canonical_url, signal)
        return list(signals.values())
