"""dev.to source: practitioner articles, scored by reactions and comments."""

import logging
import time
from collections.abc import Callable
from datetime import datetime
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict, TypeAdapter, ValidationError

from signalforge.core.artifacts.signal import RawSignal
from signalforge.plugins.sources._http import fetch_json_list

log = logging.getLogger(__name__)

API_URL = "https://dev.to/api/articles"
DEFAULT_TAGS: tuple[str, ...] = ("ai", "llm", "machinelearning")
DEFAULT_TOP_DAYS = 1
DEFAULT_MIN_REACTIONS = 20
PER_PAGE = 50


class _Article(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: int
    title: str
    url: str
    description: str = ""
    published_timestamp: str
    positive_reactions_count: int = 0
    comments_count: int = 0
    tag_list: list[str] | str = []


class DevToSource:
    name = "devto"
    source_type = "blog"

    def __init__(
        self,
        client: httpx.Client,
        *,
        tags: tuple[str, ...] = DEFAULT_TAGS,
        top_days: int = DEFAULT_TOP_DAYS,
        min_reactions: int = DEFAULT_MIN_REACTIONS,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._client = client
        self._tags = tags
        self._top_days = top_days
        self._min_reactions = min_reactions
        self._sleep = sleep

    @classmethod
    def from_config(
        cls,
        client: httpx.Client,
        cfg: dict[str, Any],
        *,
        sleep: Callable[[float], None] = time.sleep,
    ) -> "DevToSource":
        dev = cfg.get("devto") or {}
        return cls(
            client,
            tags=tuple(dev.get("tags", DEFAULT_TAGS)),
            top_days=int(dev.get("top_days", DEFAULT_TOP_DAYS)),
            min_reactions=int(dev.get("min_reactions", DEFAULT_MIN_REACTIONS)),
            sleep=sleep,
        )

    def fetch(self, since: datetime) -> list[RawSignal]:
        signals: dict[str, RawSignal] = {}
        for tag in self._tags:
            articles = fetch_json_list(
                self._client,
                API_URL,
                TypeAdapter(list[_Article]),
                label="dev.to",
                params={"tag": tag, "top": self._top_days, "per_page": PER_PAGE},
                sleep=self._sleep,
            )
            for article in articles:
                signal = self._to_signal(article, since)
                if signal is not None:
                    signals.setdefault(signal.canonical_url, signal)
        return list(signals.values())

    def _to_signal(self, article: _Article, since: datetime) -> RawSignal | None:
        if article.positive_reactions_count < self._min_reactions:
            return None
        try:
            published = datetime.fromisoformat(article.published_timestamp.replace("Z", "+00:00"))
            if published <= since:
                return None
            return RawSignal(
                source=self.name,
                source_type=self.source_type,
                canonical_url=article.url,
                title=" ".join(article.title.split()),
                summary=" ".join(article.description.split()),
                published_at=published,
                metadata={
                    "points": article.positive_reactions_count,
                    "num_comments": article.comments_count,
                },
            )
        except (ValueError, ValidationError) as exc:
            log.warning("skipping dev.to article: %s", exc, extra={"id": article.id})
            return None
