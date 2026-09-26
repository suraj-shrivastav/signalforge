from collections.abc import Callable
from datetime import UTC, datetime

import httpx
import pytest

from signalforge.core.errors import ArtifactValidationError, ProviderUnavailableError
from signalforge.plugins.sources.arxiv import ArxivSource

ATOM = b"""<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom">
<entry><title>Scaling
  Agents</title><link rel="alternate" href="http://arxiv.org/abs/2609.00001v1"/>
<published>2026-09-26T10:00:00Z</published><summary>We  study
agents.</summary></entry>
<entry><title>Old paper</title><link rel="alternate" href="http://arxiv.org/abs/2401.00001v1"/>
<published>2024-01-01T10:00:00Z</published><summary>Old.</summary></entry>
<entry><title>Undated</title><link rel="alternate" href="http://arxiv.org/abs/2609.00009v1"/></entry>
</feed>"""
REVISIONS = b"""<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom">
<entry><title>P</title><link rel="alternate" href="http://arxiv.org/abs/2609.00001v2"/>
<published>2026-09-26T10:00:00Z</published></entry>
<entry><title>P</title><link rel="alternate" href="http://arxiv.org/abs/2609.00001v1"/>
<published>2026-09-26T09:00:00Z</published></entry></feed>"""
SINCE = datetime(2026, 9, 25, tzinfo=UTC)


def _src(handler: Callable[[httpx.Request], httpx.Response]) -> ArxivSource:
    return ArxivSource(httpx.Client(transport=httpx.MockTransport(handler)), sleep=lambda _: None)


def test_fetch_filters_by_date_and_cleans_text() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, content=ATOM)

    [signal] = _src(handler).fetch(SINCE)
    assert signal.title == "Scaling Agents"
    assert signal.summary == "We study agents."
    assert signal.source_type == "paper"
    assert len(seen) == 1
    assert seen[0].url.params["search_query"] == "cat:cs.AI OR cat:cs.CL OR cat:cs.LG"
    assert seen[0].url.params["max_results"] == "100"


def test_version_suffix_is_stripped_and_revisions_dedupe() -> None:
    signals = _src(lambda _: httpx.Response(200, content=REVISIONS)).fetch(SINCE)
    assert len(signals) == 1
    assert signals[0].canonical_url.endswith("/abs/2609.00001")


def test_malformed_xml_raises() -> None:
    with pytest.raises(ArtifactValidationError):
        _src(lambda _: httpx.Response(200, content=b"<feed><entry>")).fetch(SINCE)


def test_http_503_raises_provider_unavailable() -> None:
    with pytest.raises(ProviderUnavailableError):
        _src(lambda _: httpx.Response(503)).fetch(SINCE)
