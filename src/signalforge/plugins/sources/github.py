"""GitHub source: new repositories gaining stars fast in AI topics."""

import logging
import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict, ValidationError

from signalforge.core.artifacts.signal import RawSignal
from signalforge.core.errors import ArtifactValidationError
from signalforge.plugins.sources._http import fetch_bytes

log = logging.getLogger(__name__)

API_URL = "https://api.github.com/search/repositories"
DEFAULT_TOPICS: tuple[str, ...] = ("llm", "ai-agents", "rag")
DEFAULT_CREATED_WITHIN_DAYS = 7
DEFAULT_MIN_STARS = 50
PER_PAGE = 30


class _Repo(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: int
    full_name: str
    html_url: str
    description: str | None = None
    created_at: str
    stargazers_count: int = 0
    forks_count: int = 0
    language: str | None = None
    topics: list[str] = []


class _Response(BaseModel):
    model_config = ConfigDict(extra="ignore")

    items: list[_Repo]


class GitHubSource:
    """Unauthenticated search allows ~10 requests a minute: keep the topic list short."""

    name = "github"
    source_type = "repo"

    def __init__(
        self,
        client: httpx.Client,
        *,
        topics: tuple[str, ...] = DEFAULT_TOPICS,
        created_within_days: int = DEFAULT_CREATED_WITHIN_DAYS,
        min_stars: int = DEFAULT_MIN_STARS,
        sleep: Callable[[float], None] = time.sleep,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._client = client
        self._topics = topics
        self._created_within_days = created_within_days
        self._min_stars = min_stars
        self._sleep = sleep
        self._now = now

    @classmethod
    def from_config(
        cls,
        client: httpx.Client,
        cfg: dict[str, Any],
        *,
        sleep: Callable[[float], None] = time.sleep,
    ) -> "GitHubSource":
        gh = cfg.get("github") or {}
        return cls(
            client,
            topics=tuple(gh.get("topics", DEFAULT_TOPICS)),
            created_within_days=int(gh.get("created_within_days", DEFAULT_CREATED_WITHIN_DAYS)),
            min_stars=int(gh.get("min_stars", DEFAULT_MIN_STARS)),
            sleep=sleep,
        )

    def fetch(self, since: datetime) -> list[RawSignal]:  # noqa: ARG002  (window is in days)
        # A repo that is new and starred stays interesting past one tick; ingest dedupes by URL.
        earliest = (self._now() - timedelta(days=self._created_within_days)).date().isoformat()
        signals: dict[str, RawSignal] = {}
        for topic in self._topics:
            body = fetch_bytes(
                self._client,
                API_URL,
                label="GitHub",
                params={
                    "q": f"topic:{topic} created:>{earliest} stars:>={self._min_stars}",
                    "sort": "stars",
                    "order": "desc",
                    "per_page": PER_PAGE,
                },
                sleep=self._sleep,
            )
            try:
                repos = _Response.model_validate_json(body).items
            except ValidationError as exc:
                raise ArtifactValidationError(
                    f"GitHub response has an unexpected shape: {exc}"
                ) from exc
            for repo in repos:
                signal = self._to_signal(repo)
                if signal is not None:
                    signals.setdefault(signal.canonical_url, signal)
        return list(signals.values())

    def _to_signal(self, repo: _Repo) -> RawSignal | None:
        try:
            return RawSignal(
                source=self.name,
                source_type=self.source_type,
                canonical_url=repo.html_url,
                title=repo.full_name,
                summary=" ".join((repo.description or "").split()),
                published_at=datetime.fromisoformat(repo.created_at.replace("Z", "+00:00")),
                topics=tuple(repo.topics[:8]),
                metadata={
                    "points": repo.stargazers_count,
                    "forks": repo.forks_count,
                    "language": repo.language,
                },
            )
        except (ValueError, ValidationError) as exc:
            log.warning("skipping GitHub repo: %s", exc, extra={"id": repo.id})
            return None
