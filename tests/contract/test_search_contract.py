"""Every SearchProvider must satisfy the Protocol and return SearchResults (standards §4)."""

import httpx

from signalforge.core.protocols import SearchProvider, SearchResult
from signalforge.plugins.search.tavily import TavilyClient

TAVILY_BODY = {
    "query": "q",
    "results": [
        {"url": "https://example.com/a", "title": "A", "content": "c", "score": 0.9},
        {"url": "https://example.com/b", "title": "B", "content": "c", "score": 0.8},
    ],
}


def fixture_client() -> httpx.Client:
    return httpx.Client(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=TAVILY_BODY))
    )


def test_tavily_satisfies_the_protocol_and_returns_search_results() -> None:
    provider = TavilyClient(fixture_client(), api_key="test-key", sleep=lambda _: None)
    assert isinstance(provider, SearchProvider)
    results = provider.search("q", max_results=2)
    assert results
    for result in results:
        assert isinstance(result, SearchResult)
        assert result.url.startswith("https://")
