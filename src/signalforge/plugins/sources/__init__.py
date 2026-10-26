"""Source plugins and the registry that builds them by name."""

from collections.abc import Callable
from typing import Any

import httpx

from signalforge.core.protocols import Source
from signalforge.plugins.sources._http import USER_AGENT as USER_AGENT
from signalforge.plugins.sources.arxiv import ArxivSource
from signalforge.plugins.sources.hackernews import HackerNewsSource
from signalforge.plugins.sources.huggingface import HuggingFacePapersSource
from signalforge.plugins.sources.rss import RssSource

_SOURCE_FACTORIES: dict[str, Callable[[httpx.Client, dict[str, Any]], Source]] = {
    HackerNewsSource.name: HackerNewsSource.from_config,
    RssSource.name: RssSource.from_config,
    ArxivSource.name: ArxivSource.from_config,
    HuggingFacePapersSource.name: HuggingFacePapersSource.from_config,
}
SOURCE_NAMES: tuple[str, ...] = tuple(_SOURCE_FACTORIES)


def build_source(name: str, client: httpx.Client, cfg: dict[str, Any] | None = None) -> Source:
    """Build a source by name, configured from the vertical config dict.

    Raises ``KeyError`` for an unknown name.
    """
    # The vertical config keeps per-source settings under ``sources``.
    sources = (cfg or {}).get("sources") or {}
    return _SOURCE_FACTORIES[name](client, sources)
