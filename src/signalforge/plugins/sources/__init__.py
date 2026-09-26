"""Source plugins and the registry that builds them by name."""

from collections.abc import Callable

import httpx

from signalforge.core.protocols import Source
from signalforge.plugins.sources._http import USER_AGENT as USER_AGENT
from signalforge.plugins.sources.arxiv import ArxivSource
from signalforge.plugins.sources.hackernews import HackerNewsSource
from signalforge.plugins.sources.rss import RssSource

_FACTORIES: dict[str, Callable[[httpx.Client], Source]] = {
    HackerNewsSource.name: HackerNewsSource,
    RssSource.name: RssSource,
    ArxivSource.name: ArxivSource,
}
SOURCE_NAMES: tuple[str, ...] = tuple(_FACTORIES)


def build_source(name: str, client: httpx.Client) -> Source:
    """Build a source by name. Raises ``KeyError`` for an unknown name."""
    return _FACTORIES[name](client)
