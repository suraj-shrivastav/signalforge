import json
import logging
from collections.abc import Callable
from datetime import UTC, datetime

import httpx
import pytest

from signalforge.core.errors import ArtifactValidationError, ProviderUnavailableError
from signalforge.plugins.sources.huggingface import HuggingFacePapersSource

SINCE = datetime(2026, 9, 25, tzinfo=UTC)
ITEMS = [
    {
        "paper": {"id": "2609.00001", "title": "New", "summary": "S", "upvotes": 12},
        "publishedAt": "2026-09-26T10:00:00.000Z",
    },
    {
        "paper": {"id": "2401.00001", "title": "Old", "upvotes": 1},
        "publishedAt": "2024-01-01T10:00:00.000Z",
    },
]


def _src(handler: Callable[[httpx.Request], httpx.Response]) -> HuggingFacePapersSource:
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return HuggingFacePapersSource(client, sleep=lambda _: None)


def _ok(payload: object) -> Callable[[httpx.Request], httpx.Response]:
    return lambda _r: httpx.Response(200, content=json.dumps(payload).encode())


def test_happy_path_filters_before_since() -> None:
    [signal] = _src(_ok(ITEMS)).fetch(SINCE)
    assert signal.canonical_url == "https://huggingface.co/papers/2609.00001"
    assert signal.metadata["upvotes"] == 12
    assert signal.metadata["arxiv_id"] == "2609.00001"


def test_missing_upvotes_still_works() -> None:
    items = [{"paper": {"id": "2609.00002", "title": "T"}, "publishedAt": "2026-09-26T10:00:00Z"}]
    [signal] = _src(_ok(items)).fetch(SINCE)
    assert signal.metadata["upvotes"] == 0


def test_falls_back_to_paper_published_at() -> None:
    items = [{"paper": {"id": "2609.00003", "title": "T", "publishedAt": "2026-09-26T10:00:00Z"}}]
    [signal] = _src(_ok(items)).fetch(SINCE)
    assert signal.published_at == datetime(2026, 9, 26, 10, tzinfo=UTC)


def test_bad_date_skips_only_that_item(caplog: pytest.LogCaptureFixture) -> None:
    bad = {"paper": {"id": "2609.00004", "title": "B"}, "publishedAt": "not a date"}
    with caplog.at_level(logging.WARNING):
        signals = _src(_ok([bad, *ITEMS])).fetch(SINCE)
    assert "skipping malformed" in caplog.text
    assert [s.canonical_url for s in signals] == ["https://huggingface.co/papers/2609.00001"]


def test_malformed_body_raises_validation_error() -> None:
    with pytest.raises(ArtifactValidationError):
        _src(lambda _r: httpx.Response(200, content=b"{not json")).fetch(SINCE)


def test_bad_item_shape_raises_validation_error() -> None:
    with pytest.raises(ArtifactValidationError):
        _src(_ok([{"nope": 1}])).fetch(SINCE)


def test_non_list_body_raises_validation_error() -> None:
    with pytest.raises(ArtifactValidationError):
        _src(_ok({"oops": 1})).fetch(SINCE)


def test_503_raises_provider_unavailable() -> None:
    with pytest.raises(ProviderUnavailableError):
        _src(lambda _r: httpx.Response(503)).fetch(SINCE)


def test_undated_item_is_skipped_with_warning(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING):
        assert _src(_ok([{"paper": {"id": "1", "title": "T"}}])).fetch(SINCE) == []
    assert "no publish date" in caplog.text


def test_rawsignal_failure_skips_item(caplog: pytest.LogCaptureFixture) -> None:
    items = [{"paper": {"id": "5", "title": ""}, "publishedAt": "2026-09-26T10:00:00Z"}, *ITEMS]
    with caplog.at_level(logging.WARNING):
        signals = _src(_ok(items)).fetch(SINCE)
    assert len(signals) == 1
    assert "skipping malformed" in caplog.text


def test_empty_list_returns_empty() -> None:
    assert _src(_ok([])).fetch(SINCE) == []


def test_duplicate_ids_give_one_signal() -> None:
    assert len(_src(_ok([ITEMS[0], ITEMS[0]])).fetch(SINCE)) == 1
