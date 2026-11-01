"""Hugging Face trending models: what the open-model community is adopting right now."""

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

API_URL = "https://huggingface.co/api/models"
DEFAULT_LIMIT = 50
DEFAULT_MIN_TRENDING = 50


class _Model(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    createdAt: str  # noqa: N815
    likes: int = 0
    downloads: int = 0
    trendingScore: int = 0  # noqa: N815
    pipeline_tag: str | None = None
    library_name: str | None = None
    tags: list[str] = []


class HuggingFaceModelsSource:
    """Trending, not newest: an older model can spike, and ingest dedupes by URL."""

    name = "huggingface_models"
    source_type = "model"

    def __init__(
        self,
        client: httpx.Client,
        *,
        limit: int = DEFAULT_LIMIT,
        min_trending: int = DEFAULT_MIN_TRENDING,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._client = client
        self._limit = limit
        self._min_trending = min_trending
        self._sleep = sleep

    @classmethod
    def from_config(
        cls,
        client: httpx.Client,
        cfg: dict[str, Any],
        *,
        sleep: Callable[[float], None] = time.sleep,
    ) -> "HuggingFaceModelsSource":
        hf = cfg.get("huggingface_models") or {}
        return cls(
            client,
            limit=int(hf.get("limit", DEFAULT_LIMIT)),
            min_trending=int(hf.get("min_trending", DEFAULT_MIN_TRENDING)),
            sleep=sleep,
        )

    def fetch(self, since: datetime) -> list[RawSignal]:  # noqa: ARG002  (trending, not recency)
        models = fetch_json_list(
            self._client,
            API_URL,
            TypeAdapter(list[_Model]),
            label="Hugging Face models",
            params={"sort": "trendingScore", "direction": -1, "limit": self._limit},
            sleep=self._sleep,
        )
        signals: dict[str, RawSignal] = {}
        for model in models:
            signal = self._to_signal(model)
            if signal is not None:
                signals.setdefault(signal.canonical_url, signal)
        return list(signals.values())

    def _to_signal(self, model: _Model) -> RawSignal | None:
        if model.trendingScore < self._min_trending:
            return None
        try:
            kind = model.pipeline_tag or "model"
            return RawSignal(
                source=self.name,
                source_type=self.source_type,
                canonical_url=f"https://huggingface.co/{model.id}",
                title=model.id,
                summary=f"Trending Hugging Face {kind} model ({model.library_name or 'unknown'}).",
                published_at=datetime.fromisoformat(model.createdAt.replace("Z", "+00:00")),
                topics=tuple(t for t in model.tags if ":" not in t)[:8],
                metadata={
                    "points": model.trendingScore,
                    "likes": model.likes,
                    "downloads": model.downloads,
                },
            )
        except (ValueError, ValidationError) as exc:
            log.warning("skipping Hugging Face model: %s", exc, extra={"id": model.id})
            return None
