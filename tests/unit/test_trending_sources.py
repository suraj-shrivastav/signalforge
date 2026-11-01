from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest

from signalforge.core.errors import ArtifactValidationError
from signalforge.plugins.sources.devto import DevToSource
from signalforge.plugins.sources.github import GitHubSource
from signalforge.plugins.sources.huggingface_models import HuggingFaceModelsSource
from signalforge.plugins.sources.lobsters import LobstersSource

SINCE = datetime(2026, 9, 1, tzinfo=UTC)


def client(body: Any, seen: list[httpx.Request] | None = None) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(request)
        return httpx.Response(200, json=body)

    return httpx.Client(transport=httpx.MockTransport(handler))


def lobsters_story(n: int, **extra: Any) -> dict[str, Any]:
    return {
        "short_id": f"s{n}",
        "created_at": "2026-09-26T10:00:00.000-05:00",
        "title": f"Story {n}",
        "url": f"https://example.com/{n}",
        "score": 20,
        "comment_count": 4,
        **extra,
    }


def test_lobsters_maps_score_to_points_and_skips_text_posts_and_low_scores() -> None:
    body = [
        lobsters_story(1),
        lobsters_story(2, url=""),
        lobsters_story(3, score=1),
        lobsters_story(4, created_at="2026-08-01T10:00:00.000-05:00"),
    ]
    source = LobstersSource(client(body), tags=("ai",))
    signals = source.fetch(SINCE)
    assert [s.title for s in signals] == ["Story 1"]
    assert signals[0].metadata["points"] == 20
    assert signals[0].metadata["num_comments"] == 4


def test_lobsters_dedupes_a_story_listed_under_two_tags() -> None:
    source = LobstersSource(client([lobsters_story(1)]), tags=("ai", "ml"))
    assert len(source.fetch(SINCE)) == 1


def test_lobsters_wrong_shape_fails_loud() -> None:
    with pytest.raises(ArtifactValidationError):
        LobstersSource(client({"not": "a list"}), tags=("ai",)).fetch(SINCE)


def devto_article(n: int, **extra: Any) -> dict[str, Any]:
    return {
        "id": n,
        "title": f"Post {n}",
        "url": f"https://dev.to/a/{n}",
        "description": "About  things",
        "published_timestamp": "2026-09-26T10:00:00Z",
        "positive_reactions_count": 40,
        "comments_count": 6,
        **extra,
    }


def test_devto_filters_by_reactions_and_date() -> None:
    body = [
        devto_article(1),
        devto_article(2, positive_reactions_count=2),
        devto_article(3, published_timestamp="2026-08-01T10:00:00Z"),
    ]
    signals = DevToSource(client(body), tags=("ai",)).fetch(SINCE)
    assert [s.title for s in signals] == ["Post 1"]
    assert signals[0].summary == "About things"
    assert signals[0].metadata["points"] == 40


def test_devto_sends_tag_and_window() -> None:
    seen: list[httpx.Request] = []
    DevToSource(client([], seen), tags=("llm",), top_days=3).fetch(SINCE)
    assert seen[0].url.params["tag"] == "llm"
    assert seen[0].url.params["top"] == "3"


def repo(n: int, **extra: Any) -> dict[str, Any]:
    return {
        "id": n,
        "full_name": f"org/repo{n}",
        "html_url": f"https://github.com/org/repo{n}",
        "description": "An agent  framework",
        "created_at": "2026-09-26T10:00:00Z",
        "stargazers_count": 400,
        "forks_count": 12,
        "topics": ["llm", "agents"],
        **extra,
    }


def test_github_maps_stars_to_points_and_queries_by_topic_and_age() -> None:
    seen: list[httpx.Request] = []
    now: Callable[[], datetime] = lambda: datetime(2026, 9, 30, tzinfo=UTC)  # noqa: E731
    source = GitHubSource(
        client({"items": [repo(1)]}, seen),
        topics=("llm",),
        created_within_days=7,
        min_stars=50,
        now=now,
    )
    signals = source.fetch(SINCE)
    assert signals[0].title == "org/repo1"
    assert signals[0].metadata["points"] == 400
    assert signals[0].topics == ("llm", "agents")
    query = seen[0].url.params["q"]
    assert "topic:llm" in query
    assert "created:>2026-09-23" in query
    assert "stars:>=50" in query


def test_github_wrong_shape_fails_loud() -> None:
    with pytest.raises(ArtifactValidationError):
        GitHubSource(client([1, 2]), topics=("llm",)).fetch(SINCE)


def hf_model(model_id: str, score: int, **extra: Any) -> dict[str, Any]:
    return {
        "id": model_id,
        "createdAt": "2026-09-26T10:00:00.000Z",
        "trendingScore": score,
        "likes": 900,
        "downloads": 15000,
        "pipeline_tag": "text-generation",
        "tags": ["llm", "license:apache-2.0", "region:us"],
        **extra,
    }


def test_hf_models_keep_only_trending_ones_and_drop_key_value_tags() -> None:
    body = [hf_model("org/hot", 700), hf_model("org/cold", 3)]
    signals = HuggingFaceModelsSource(client(body)).fetch(SINCE)
    assert [s.title for s in signals] == ["org/hot"]
    assert signals[0].canonical_url == "https://huggingface.co/org/hot"
    assert signals[0].metadata["points"] == 700
    assert signals[0].topics == ("llm",)


def test_hf_models_ask_for_trending_order() -> None:
    seen: list[httpx.Request] = []
    HuggingFaceModelsSource(client([], seen), limit=10).fetch(SINCE)
    assert seen[0].url.params["sort"] == "trendingScore"
    assert seen[0].url.params["limit"] == "10"
