"""Research reports why a card is not 'researched' instead of failing silently."""

import uuid
from types import SimpleNamespace
from typing import Any

from signalforge.core.artifacts.research import ResearchStatus
from signalforge.core.errors import ProviderRejectedError
from signalforge.stages.research import _process_card


class DownFetcher:
    def fetch_html(self, url: str, *, max_attempts: int | None = None) -> str:  # noqa: ARG002
        raise ProviderRejectedError("blocked", context={"status": 403})


def test_unfetchable_primary_source_has_a_reason() -> None:
    card = SimpleNamespace(id=uuid.uuid4())
    signal = SimpleNamespace(canonical_url="https://example.com/x", title="t", source="rss")
    package, reason = _process_card(
        None,  # type: ignore[arg-type]
        DownFetcher(),
        None,  # type: ignore[arg-type]
        card,  # type: ignore[arg-type]
        signal,  # type: ignore[arg-type]
        uuid.uuid4(),
    )
    assert package.status is ResearchStatus.NEEDS_MORE_INFO
    assert reason is not None
    assert "primary source" in reason


def test_template_follows_card_format_for_blog_posts() -> None:
    from signalforge.core.artifacts.article import ArticleTemplate
    from signalforge.stages.draft_extraction import select_template

    args: dict[str, Any] = {"source_type": "blog", "topics": [], "title": "Kumo Forecast adds X"}
    assert select_template(card_format="deep_dive", **args) is ArticleTemplate.EXPLAINER
