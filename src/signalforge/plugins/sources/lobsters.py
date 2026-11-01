"""Lobsters source: community-curated links, scored by votes and discussion."""

import logging
import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict, TypeAdapter, ValidationError

from signalforge.core.artifacts.signal import RawSignal
from signalforge.plugins.sources._http import fetch_json_list

log = logging.getLogger(__name__)

API_URL = "https://lobste.rs/t/{tag}.json"
DEFAULT_TAGS: tuple[str, ...] = ("ai", "ml")
DEFAULT_MIN_SCORE = 5


class _Story(BaseModel):
    model_config = ConfigDict(extra="ignore")

    short_id: str
    created_at: str
    title: str
    url: str = ""
    score: int = 0
    comment_count: int = 0
    comments_url: str = ""
    tags: list[str] = []


class LobstersSource:
    name = "lobsters"
    source_type = "community"

    def __init__(
        self,
        client: httpx.Client,
        *,
        tags: tuple[str, ...] = DEFAULT_TAGS,
        min_score: int = DEFAULT_MIN_SCORE,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._client = client
        self._tags = tags
        self._min_score = min_score
        self._sleep = sleep

    @classmethod
    def from_config(
        cls,
        client: httpx.Client,
        cfg: dict[str, Any],
        *,
        sleep: Callable[[float], None] = time.sleep,
    ) -> "LobstersSource":
        lob = cfg.get("lobsters") or {}
        return cls(
            client,
            tags=tuple(lob.get("tags", DEFAULT_TAGS)),
            min_score=int(lob.get("min_score", DEFAULT_MIN_SCORE)),
            sleep=sleep,
        )

    def fetch(self, since: datetime) -> list[RawSignal]:
        signals: dict[str, RawSignal] = {}
        for tag in self._tags:
            stories = fetch_json_list(
                self._client,
                API_URL.format(tag=tag),
                TypeAdapter(list[_Story]),
                label="Lobsters",
                sleep=self._sleep,
            )
            for story in stories:
                signal = self._to_signal(story, since)
                if signal is not None:
                    signals.setdefault(signal.canonical_url, signal)
        return list(signals.values())

    def _to_signal(self, story: _Story, since: datetime) -> RawSignal | None:
        if not story.url or story.score < self._min_score:  # text posts have no page to research
            return None
        try:
            published = datetime.fromisoformat(story.created_at)
            if published.tzinfo is None:
                published = published.replace(tzinfo=UTC)
            if published <= since:
                return None
            return RawSignal(
                source=self.name,
                source_type=self.source_type,
                canonical_url=story.url,
                title=" ".join(story.title.split()),
                published_at=published,
                metadata={
                    "points": story.score,
                    "num_comments": story.comment_count,
                    "lobsters_url": story.comments_url,
                    "tags": story.tags,
                },
            )
        except (ValueError, ValidationError) as exc:
            log.warning("skipping Lobsters story: %s", exc, extra={"id": story.short_id})
            return None
