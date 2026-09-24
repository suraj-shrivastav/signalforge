"""Source plugins and the registry that builds them by name."""

from collections.abc import Callable

import httpx

from signalforge.core.protocols import Source
from signalforge.plugins.sources.hackernews import HackerNewsSource

USER_AGENT = "signalforge/0.1 (+https://github.com/suraj-shrivastav/signalforge)"

_FACTORIES: dict[str, Callable[[httpx.Client], Source]] = {
    HackerNewsSource.name: HackerNewsSource,
}
SOURCE_NAMES: tuple[str, ...] = tuple(_FACTORIES)


def build_source(name: str, client: httpx.Client) -> Source:
    """Build a source by name. Raises ``KeyError`` for an unknown name."""
    return _FACTORIES[name](client)
