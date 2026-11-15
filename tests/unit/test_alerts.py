import json
import logging

import httpx
import pytest

from signalforge.alerts import send_alert


def client(status: int, seen: list[httpx.Request]) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(status)

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_posts_slack_and_discord_compatible_payload() -> None:
    seen: list[httpx.Request] = []
    sent = send_alert(
        "https://hooks.example/x", "paused", "canary failed", client=client(200, seen)
    )
    assert sent
    body = json.loads(seen[0].content)
    assert body["text"] == body["content"] == "[SignalForge] paused: canary failed"


def test_no_url_is_a_noop() -> None:
    assert send_alert(None, "paused", "x") is False


def test_failure_never_raises() -> None:
    seen: list[httpx.Request] = []
    assert send_alert("https://hooks.example/x", "t", "d", client=client(500, seen)) is False

    def boom(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down")

    broken = httpx.Client(transport=httpx.MockTransport(boom))
    assert send_alert("https://hooks.example/x", "t", "d", client=broken) is False


def test_invalid_url_returns_false_without_raising() -> None:
    assert send_alert("https://hooks.example/\x00secret", "t", "d") is False


def test_url_never_appears_in_logs(caplog: pytest.LogCaptureFixture) -> None:
    url = "https://hooks.example/SECRET-TOKEN"
    seen: list[httpx.Request] = []

    def boom(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError(f"cannot reach {url}")

    broken = httpx.Client(transport=httpx.MockTransport(boom))
    with caplog.at_level(logging.DEBUG):
        send_alert(url, "t", "d", client=broken)
        send_alert(url, "t", "d", client=client(500, seen))
        send_alert(url + "\x00", "t", "d")
        send_alert(None, "t", "d")
    ours = [r for r in caplog.records if r.name == "signalforge.alerts"]
    assert len(ours) == 4
    for record in ours:
        assert "SECRET-TOKEN" not in json.dumps(record.__dict__, default=str)
