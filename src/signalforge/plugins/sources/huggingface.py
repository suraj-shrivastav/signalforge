"""Hugging Face daily papers source."""

import logging
import time
from collections.abc import Callable
from datetime import UTC, datetime

import httpx
from pydantic import BaseModel, ConfigDict, TypeAdapter, ValidationError

from signalforge.core.artifacts.signal import RawSignal
from signalforge.core.errors import ArtifactValidationError
from signalforge.plugins.sources._http import fetch_bytes

log = logging.getLogger(__name__)

API_URL = "https://huggingface.co/api/daily_papers"


class _Paper(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    title: str
    summary: str | None = None
    upvotes: int | None = None
    publishedAt: str | None = None  # noqa: N815


class _Item(BaseModel):
    model_config = ConfigDict(extra="ignore")

    paper: _Paper
    publishedAt: str | None = None  # noqa: N815


def _parse_date(raw: str) -> datetime:
    parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


class HuggingFacePapersSource:
    name = "huggingface"
    source_type = "paper"

    def __init__(
        self,
        client: httpx.Client,
        *,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._client = client
        self._sleep = sleep

    def fetch(self, since: datetime) -> list[RawSignal]:
        body = fetch_bytes(self._client, API_URL, label="Hugging Face", sleep=self._sleep)
        # Bad item SHAPE fails the whole run (fail loud on schema drift);
        # a bad date or RawSignal failure skips only that item.
        try:
            items = TypeAdapter(list[_Item]).validate_json(body)
        except ValidationError as exc:
            raise ArtifactValidationError(
                f"Hugging Face daily papers response has an unexpected shape: {exc}"
            ) from exc
        signals: dict[str, RawSignal] = {}
        for item in items:
            paper = item.paper
            raw_date = item.publishedAt or paper.publishedAt
            if raw_date is None:
                log.warning("skipping Hugging Face paper: no publish date", extra={"id": paper.id})
                continue
            try:
                published = _parse_date(raw_date)
                if published <= since:
                    continue
                signal = RawSignal(
                    source=self.name,
                    source_type=self.source_type,
                    canonical_url=f"https://huggingface.co/papers/{paper.id}",
                    title=" ".join(paper.title.split()),
                    summary=" ".join((paper.summary or "").split()),
                    published_at=published,
                    metadata={"upvotes": paper.upvotes or 0, "arxiv_id": paper.id},
                )
            except (ValueError, ValidationError) as exc:
                log.warning(
                    "skipping malformed Hugging Face paper: %s", exc, extra={"id": paper.id}
                )
                continue
            signals.setdefault(signal.canonical_url, signal)
        return list(signals.values())
