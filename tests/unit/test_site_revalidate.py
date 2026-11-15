import httpx
import pytest

from signalforge.site_revalidate import revalidate_site


def test_posts_the_secret_to_the_revalidate_route(monkeypatch: pytest.MonkeyPatch) -> None:
    sent: dict[str, object] = {}

    def fake_post(url: str, headers: dict[str, str], **_kw: object) -> httpx.Response:
        sent.update(url=url, headers=headers)
        return httpx.Response(200)

    monkeypatch.setattr(httpx, "post", fake_post)
    assert revalidate_site("https://example.com/", "s3cret") is True
    assert sent == {
        "url": "https://example.com/api/revalidate",
        "headers": {"x-revalidate-secret": "s3cret"},
    }


def test_skips_without_site_or_secret() -> None:
    assert revalidate_site("", "s") is False
    assert revalidate_site("https://example.com", "") is False


def test_rejection_and_network_errors_return_false(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(httpx, "post", lambda *_a, **_k: httpx.Response(401))
    assert revalidate_site("https://example.com", "s") is False

    def boom(*_a: object, **_k: object) -> httpx.Response:
        raise httpx.ConnectError("down")

    monkeypatch.setattr(httpx, "post", boom)
    assert revalidate_site("https://example.com", "s") is False
