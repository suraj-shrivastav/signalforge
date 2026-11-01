from datetime import UTC, datetime

import httpx

from signalforge.plugins.sources import build_source
from signalforge.plugins.sources.arxiv import ArxivSource
from signalforge.plugins.sources.hackernews import FRONT_PAGE_URL, HackerNewsSource
from signalforge.plugins.sources.rss import RssSource
from signalforge.verticals.config import load_vertical, source_enabled

SINCE = datetime(2026, 9, 23, tzinfo=UTC)


def test_default_vertical_loads_with_the_expected_sources() -> None:
    cfg = load_vertical()
    assert cfg["name"] == "ai_engineering"
    assert set(cfg["sources"]) == {
        "hackernews",
        "rss",
        "arxiv",
        "huggingface",
        "huggingface_models",
        "github",
        "lobsters",
        "devto",
    }


def test_build_source_reads_per_source_settings_under_sources() -> None:
    client = httpx.Client()
    hn = build_source("hackernews", client, cfg=load_vertical())
    assert isinstance(hn, HackerNewsSource)
    assert hn._trending_enabled is True
    assert hn._trending_min_points == 40
    arxiv = build_source("arxiv", client, cfg=load_vertical())
    assert isinstance(arxiv, ArxivSource)
    assert arxiv._categories == ("cs.AI", "cs.CL", "cs.LG")
    rss = build_source("rss", client, cfg=load_vertical())
    assert isinstance(rss, RssSource)
    assert len(rss._feeds) >= 6


def test_without_config_trending_stays_off() -> None:
    hn = build_source("hackernews", httpx.Client())
    assert isinstance(hn, HackerNewsSource)
    assert hn._trending_enabled is False


def test_null_trending_block_does_not_crash() -> None:
    cfg = {"sources": {"hackernews": {"trending": None}}}
    hn = build_source("hackernews", httpx.Client(), cfg=cfg)
    assert isinstance(hn, HackerNewsSource)
    assert hn._trending_enabled is False


def test_source_enabled_defaults_on_and_honours_false() -> None:
    cfg = {"sources": {"rss": {"enabled": False}, "arxiv": {}}}
    assert source_enabled(cfg, "rss") is False
    assert source_enabled(cfg, "arxiv") is True
    assert source_enabled(cfg, "huggingface") is True
    assert source_enabled({}, "rss") is True


def test_trending_fetch_hits_the_front_page_and_dedupes_against_search() -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url).split("?")[0])
        hit = {
            "objectID": "1",
            "title": "Story",
            "url": "https://example.com/1",
            "created_at_i": 1790223659,
            "points": 300,
            "num_comments": 120,
            "author": "a",
        }
        return httpx.Response(200, json={"hits": [hit]})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    source = HackerNewsSource(client, queries=("LLM",), trending_enabled=True, sleep=lambda _: None)
    signals = source.fetch(SINCE)
    assert FRONT_PAGE_URL in seen
    assert len(signals) == 1
