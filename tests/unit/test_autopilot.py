import json
from collections.abc import Callable
from datetime import UTC, datetime

import httpx
import pytest
from apps.worker import autopilot

Handler = Callable[[httpx.Request], httpx.Response]


def api(routes: dict[tuple[str, str], object], calls: list[str]) -> autopilot.Api:
    def handler(request: httpx.Request) -> httpx.Response:
        key = (request.method, request.url.path)
        calls.append(f"{request.method} {request.url.path}")
        body = routes.get(key, {})
        if isinstance(body, int):
            return httpx.Response(body, json={})
        return httpx.Response(200, json=body)

    client = httpx.Client(base_url="https://api.test", transport=httpx.MockTransport(handler))
    return autopilot.Api(client, sleep=lambda _s: None)


UNPAUSED = {"paused": False, "paused_reason": None, "paused_by": None, "paused_until": None,
            "slot": None, "slot_status": None, "slot_failures": 0}  # fmt: skip


def test_paused_does_nothing() -> None:
    calls: list[str] = []
    a = api({("GET", "/agent/controls"): {**UNPAUSED, "paused": True}}, calls)
    assert autopilot.run_once(a, now=datetime(2026, 11, 15, 6, tzinfo=UTC), env={}) == 0
    assert calls == ["GET /agent/controls"]


def test_closes_dead_end_cards_with_reason_tag() -> None:
    calls: list[str] = []
    sent: list[dict[str, object]] = []
    card = {
        "card_id": "c1",
        "title": "t",
        "stage": "research_parked",
        "next_action": "close",
        "slug": None,
    }

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(f"{request.method} {request.url.path}")
        if request.url.path == "/agent/work":
            return httpx.Response(200, json={"counts": {"close": 1}, "cards": [card]})
        if request.url.path == "/cards/c1/decision":
            sent.append(json.loads(request.content))
            return httpx.Response(201, json={})
        return httpx.Response(200, json={})

    client = httpx.Client(base_url="https://api.test", transport=httpx.MockTransport(handler))
    autopilot.close_dead_ends(autopilot.Api(client, sleep=lambda _s: None))
    assert sent == [{"decision": "rejected", "reason_tags": ["needs_more_evidence"],
                     "note": "auto-closed: research_parked"}]  # fmt: skip


def test_unclaimed_slot_skips_pipeline() -> None:
    calls: list[str] = []
    a = api(
        {
            ("GET", "/agent/controls"): UNPAUSED,
            ("GET", "/agent/work"): {"counts": {}, "cards": []},
            ("POST", "/agent/publish-next"): {
                "published": None,
                "waiting": 0,
                "next_publish_at": None,
            },
            ("POST", "/agent/controls/slot/claim"): {"claimed": False, "slot": "s", "failures": 0},
        },
        calls,
    )
    assert autopilot.run_once(a, now=datetime(2026, 11, 15, 6, tzinfo=UTC), env={}) == 0
    assert "POST /agent/run/tick" not in calls


def test_wait_stage_treats_errors_as_unknown() -> None:
    replies = iter([httpx.Response(502), httpx.Response(200, json={"running": None, "last": {}})])
    client = httpx.Client(
        base_url="https://api.test", transport=httpx.MockTransport(lambda _r: next(replies))
    )
    assert autopilot.Api(client, sleep=lambda _s: None).wait_stage("tick") is True


def test_wait_stage_gives_up_after_max_polls() -> None:
    client = httpx.Client(
        base_url="https://api.test",
        transport=httpx.MockTransport(
            lambda _r: httpx.Response(200, json={"running": {"stage": "tick"}, "last": {}})
        ),
    )
    assert autopilot.Api(client, sleep=lambda _s: None).wait_stage("tick", polls=3) is False


@pytest.mark.parametrize(("hour", "slot"), [(0, "2026-11-15-00"), (13, "2026-11-15-12")])
def test_slot_uses_configured_timezone(hour: int, slot: str) -> None:
    now = datetime(2026, 11, 15, hour, 30, tzinfo=UTC)
    assert autopilot.current_slot(now, "UTC") == slot


def test_accept_best_cards_uses_real_queue_shape() -> None:
    from typing import Any, cast
    from uuid import uuid4

    from apps.api.schemas import CardOut, QueueSignalOut

    def card(score: float, status: str) -> dict[str, object]:
        return CardOut(
            id=uuid4(), schema_version=1, what_happened="w", why_it_matters="y", novelty=0.5,
            signal_strength=0.5, coverage_gap="g", suggested_angle="a", format="explainer",
            evergreen_score=0.5, confidence=0.5, risk_flags=[], prompt_version="p", model="m",
            signal=QueueSignalOut(id=uuid4(), title="t", source="s", canonical_url="https://x.test"),
            score=score, wildcard=False, status=cast(Any, status), created_at=datetime.now(UTC),
        ).model_dump(mode="json")  # fmt: skip

    queue = [
        card(0.2, "proposed"),
        card(0.9, "snoozed"),
        card(0.8, "proposed"),
        card(0.5, "proposed"),
    ]
    sent: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/cards/queue":
            return httpx.Response(200, json=queue)
        sent.append(request.url.path)
        assert json.loads(request.content)["decision"] == "accepted"
        return httpx.Response(201, json={})

    client = httpx.Client(base_url="https://api.test", transport=httpx.MockTransport(handler))
    n = autopilot.accept_best_cards(autopilot.Api(client, sleep=lambda _s: None), 2)
    assert n == 2
    assert sent == [f"/cards/{queue[2]['id']}/decision", f"/cards/{queue[3]['id']}/decision"]


def _flow(claim: dict[str, object], tick: object, calls: list[str]) -> autopilot.Api:
    routes: dict[tuple[str, str], object] = {
        ("GET", "/agent/controls"): UNPAUSED,
        ("GET", "/agent/work"): {"counts": {}, "cards": []},
        ("POST", "/agent/publish-next"): {"published": None, "waiting": 0, "next_publish_at": None},
        ("POST", "/agent/controls/slot/claim"): claim,
        ("POST", "/agent/run/tick"): tick,
    }
    return api(routes, calls)


def test_unclaimed_slot_is_never_finished() -> None:
    calls: list[str] = []
    a = _flow({"claimed": False, "slot": "s", "failures": 0}, {}, calls)
    autopilot.run_once(a, now=datetime(2026, 11, 15, 6, tzinfo=UTC), env={})
    assert "POST /agent/controls/slot/finish" not in calls


def test_paused_after_claim_finishes_slot_not_ok_and_exits_zero() -> None:
    calls: list[str] = []
    a = _flow({"claimed": True, "slot": "s", "failures": 0}, 423, calls)
    assert autopilot.run_once(a, now=datetime(2026, 11, 15, 6, tzinfo=UTC), env={}) == 0
    assert calls[-1] == "POST /agent/controls/slot/finish"


def test_failed_claimed_slot_alerts_on_third_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    sent: list[tuple[str | None, str]] = []

    def fake_alert(url: str | None, title: str, _detail: str) -> bool:
        sent.append((url, title))
        return True

    monkeypatch.setattr(autopilot, "send_alert", fake_alert)
    calls: list[str] = []
    a = _flow({"claimed": True, "slot": "s", "failures": 2}, {"started": False}, calls)
    env = {"ALERT_WEBHOOK_URL": "https://hook.test/x"}
    assert autopilot.run_once(a, now=datetime(2026, 11, 15, 6, tzinfo=UTC), env=env) == 1
    assert calls[-1] == "POST /agent/controls/slot/finish"
    assert sent == [("https://hook.test/x", "slot failed 3 times")]


def test_revise_is_not_run_after_the_last_review_try() -> None:
    calls: list[str] = []
    routes: dict[tuple[str, str], object] = {
        ("GET", "/agent/work"): {
            "counts": {},
            "cards": [
                {
                    "card_id": "c1",
                    "title": "t",
                    "stage": "s",
                    "next_action": "auto_review",
                    "slug": None,
                }
            ],
        },
        ("POST", "/agent/drafts/c1/auto-review"): {"action": "revise", "reasons": []},
        ("POST", "/agent/run/revise"): {"started": True, "stage": "revise"},
        ("GET", "/agent/runs"): {"running": None, "last": {}},
        ("POST", "/agent/publish-next"): {"published": None, "waiting": 0, "next_publish_at": None},
    }
    a = api(routes, calls)
    autopilot.review_cards(a, {})
    assert calls.count("POST /agent/drafts/c1/auto-review") == 3
    assert calls.count("POST /agent/run/revise") == 2
