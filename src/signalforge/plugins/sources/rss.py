"""Generic RSS/Atom source. Covers lab blogs and GitHub release feeds."""

import logging
import time
from collections.abc import Callable, Sequence
from datetime import datetime

import httpx
from pydantic import ValidationError

from signalforge.core.artifacts.signal import RawSignal
from signalforge.core.errors import ProviderUnavailableError, SignalForgeError
from signalforge.plugins.sources._http import fetch_bytes
from signalforge.plugins.sources.feeds import parse_feed

log = logging.getLogger(__name__)

# ponytail: hard-coded until the vertical config (ai_engineering.yaml) exists.
DEFAULT_FEEDS: tuple[str, ...] = (
    "https://openai.com/news/rss.xml",
    "https://deepmind.google/blog/rss.xml",
    "https://huggingface.co/blog/feed.xml",
    "https://github.com/ollama/ollama/releases.atom",
    "https://github.com/vllm-project/vllm/releases.atom",
    "https://github.com/langchain-ai/langchain/releases.atom",
)


class RssSource:
    name = "rss"
    source_type = "blog"

    def __init__(
        self,
        client: httpx.Client,
        *,
        feeds: Sequence[str] = DEFAULT_FEEDS,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._client = client
        self._feeds = tuple(feeds)
        self._sleep = sleep

    def fetch(self, since: datetime) -> list[RawSignal]:
        signals: dict[str, RawSignal] = {}
        failures = 0
        for feed in self._feeds:
            try:
                entries = parse_feed(
                    fetch_bytes(self._client, feed, label="Feed", sleep=self._sleep)
                )
            except SignalForgeError:
                failures += 1
                log.warning("feed failed: %s", feed, extra={"feed": feed}, exc_info=True)
                continue
            for entry in entries:
                if entry.published is None or entry.published <= since:
                    continue
                try:
                    signal = RawSignal(
                        source=self.name,
                        source_type=self.source_type,
                        canonical_url=entry.link,
                        title=entry.title,
                        summary=entry.summary,
                        published_at=entry.published,
                        metadata={"feed": feed},
                    )
                except ValidationError:
                    log.warning("skipping malformed entry in %s", feed, extra={"feed": feed})
                    continue
                signals.setdefault(signal.canonical_url, signal)
        if self._feeds and failures == len(self._feeds):
            raise ProviderUnavailableError("Every feed failed")
        return list(signals.values())
