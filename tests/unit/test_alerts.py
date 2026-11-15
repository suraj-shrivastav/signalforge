import json

import httpx

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
