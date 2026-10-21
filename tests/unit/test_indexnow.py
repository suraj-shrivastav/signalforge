import httpx
import pytest

from signalforge.indexnow import ping_indexnow


def test_posts_the_article_url_with_key_location(monkeypatch: pytest.MonkeyPatch) -> None:
    sent: dict[str, object] = {}

    def fake_post(url: str, json: dict[str, object], **_kw: object) -> httpx.Response:
        sent.update(url=url, json=json)
        return httpx.Response(202)

    monkeypatch.setattr(httpx, "post", fake_post)
    assert ping_indexnow("https://example.com/", "k1", "a-title") is True
    assert sent["json"] == {
        "host": "example.com",
        "key": "k1",
        "keyLocation": "https://example.com/indexnow-key.txt",
        "urlList": ["https://example.com/articles/a-title"],
    }


def test_skips_without_site_or_key() -> None:
    assert ping_indexnow("", "k", "s") is False
    assert ping_indexnow("https://example.com", "", "s") is False


def test_rejection_and_network_errors_return_false(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(httpx, "post", lambda *_a, **_k: httpx.Response(403))
    assert ping_indexnow("https://example.com", "k", "s") is False

    def boom(*_a: object, **_k: object) -> httpx.Response:
        raise httpx.ConnectError("down")

    monkeypatch.setattr(httpx, "post", boom)
    assert ping_indexnow("https://example.com", "k", "s") is False
