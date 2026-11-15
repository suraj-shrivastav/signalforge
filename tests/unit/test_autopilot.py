import json
from collections.abc import Callable
from datetime import UTC, datetime

import httpx
import pytest
from apps.worker import autopilot

Handler = Callable[[httpx.Request], httpx.Response]


def api(
    routes: dict[tuple[str, str], object],
    calls: list[str],
    sent: dict[str, object] | None = None,
) -> autopilot.Api:
    def handler(request: httpx.Request) -> httpx.Response:
        key = (request.method, request.url.path)
        calls.append(f"{request.method} {request.url.path}")
        if sent is not None and request.content:
            sent[request.url.path] = json.loads(request.content)
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


def test_closes_dead_end_cards_with_reason_tag(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level("INFO", logger="autopilot")
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
    assert "auto-closed c1 (research_parked): t" in caplog.text  # 13: the record of closed cards


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
    assert autopilot.Api(client, sleep=lambda _s: None).wait_stage("tick") == {
        "running": None,
        "last": {},
    }


def test_wait_stage_gives_up_after_max_polls() -> None:
    client = httpx.Client(
        base_url="https://api.test",
        transport=httpx.MockTransport(
            lambda _r: httpx.Response(200, json={"running": {"stage": "tick"}, "last": {}})
        ),
    )
    assert autopilot.Api(client, sleep=lambda _s: None).wait_stage("tick", polls=3) is None


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
        ("GET", "/agent/runs"): {"running": None, "last": {"revise": {"ok": True}}},
        ("POST", "/agent/publish-next"): {"published": None, "waiting": 0, "next_publish_at": None},
    }
    a = api(routes, calls)
    autopilot.review_cards(a, {})
    assert calls.count("POST /agent/drafts/c1/auto-review") == 3
    assert calls.count("POST /agent/run/revise") == 2


# --- final fix wave (FW-A) ---------------------------------------------------------------

NOW = datetime(2026, 11, 15, 6, tzinfo=UTC)
ALL_OK = {
    "running": None,
    "last": {s: {"ok": True} for s in ("tick", "research", "draft", "revise")},
}


def _card(card_id: str, action: str) -> dict[str, object]:
    return {"card_id": card_id, "title": "t", "stage": "s", "next_action": action, "slug": None}


def _slot_routes(cards: list[dict[str, object]], **extra: object) -> dict[tuple[str, str], object]:
    routes: dict[tuple[str, str], object] = {
        ("GET", "/agent/controls"): UNPAUSED,
        ("GET", "/agent/work"): {"counts": {}, "cards": cards},
        ("GET", "/agent/pipeline"): {"counts": {}, "cards": cards},
        ("GET", "/agent/runs"): ALL_OK,
        ("GET", "/cards/queue"): [],
        ("POST", "/agent/publish-next"): {"published": None, "waiting": 0, "next_publish_at": None},
        ("POST", "/agent/controls/slot/claim"): {"claimed": True, "slot": "s", "failures": 0},
        ("POST", "/agent/run/tick"): {"started": True, "stage": "tick"},
        ("POST", "/agent/run/research"): {"started": True, "stage": "research"},
        ("POST", "/agent/run/draft"): {"started": True, "stage": "draft"},
        ("POST", "/agent/run/revise"): {"started": True, "stage": "revise"},
    }
    for key, value in extra.items():
        method, path = key.split(" ", 1)
        routes[(method, path)] = value
    return routes


def test_slot_starts_revise_for_cards_already_waiting_on_it() -> None:  # 3a
    calls: list[str] = []
    a = api(_slot_routes([_card("c1", "run_revise")]), calls)
    assert autopilot.run_slot(a, {}, first_try=False) is None
    assert calls.count("POST /agent/run/revise") == 1


def test_review_skips_a_card_the_api_refuses_with_409() -> None:  # 3b
    calls: list[str] = []
    routes = _slot_routes(
        [_card("c1", "auto_review"), _card("c2", "auto_review")],
        **{"POST /agent/drafts/c1/auto-review": 409,
           "POST /agent/drafts/c2/auto-review": {"action": "approve", "reasons": []}},
    )  # fmt: skip
    autopilot.review_cards(api(routes, calls), {})
    assert "POST /agent/drafts/c2/auto-review" in calls


def test_any_error_after_the_claim_finishes_the_slot_not_ok_and_alerts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:  # 4a
    alerts: list[str] = []
    monkeypatch.setattr(autopilot, "send_alert", lambda _u, title, _d: alerts.append(title))

    def boom(*_a: object, **_k: object) -> None:
        raise ValueError("bad")

    monkeypatch.setattr(autopilot, "run_slot", boom)
    calls: list[str] = []
    sent: dict[str, object] = {}
    claim = {"claimed": True, "slot": "s", "failures": 2}
    routes = _slot_routes([], **{"POST /agent/controls/slot/claim": claim})
    assert autopilot.run_once(api(routes, calls, sent), NOW, {}) == 1
    assert sent["/agent/controls/slot/finish"] == {"slot": "2026-11-15-06", "ok": False}
    assert alerts == ["slot failed 3 times"]


def test_a_failing_finish_call_still_alerts(monkeypatch: pytest.MonkeyPatch) -> None:  # 4b
    alerts: list[str] = []
    monkeypatch.setattr(autopilot, "send_alert", lambda _u, title, _d: alerts.append(title))
    calls: list[str] = []
    routes = _slot_routes(
        [], **{"POST /agent/controls/slot/claim": {"claimed": True, "slot": "s", "failures": 2},
               "POST /agent/run/tick": {"started": False}, "POST /agent/controls/slot/finish": 500},
    )  # fmt: skip
    assert autopilot.run_once(api(routes, calls), NOW, {}) == 1
    assert alerts == ["slot failed 3 times"]


def test_a_broken_pre_claim_step_does_not_block_the_slot() -> None:  # 4c
    calls: list[str] = []
    routes = _slot_routes(
        [], **{"POST /agent/publish-next": 400,
               "POST /agent/controls/slot/claim": {"claimed": False, "slot": "s", "failures": 0}},
    )  # fmt: skip
    assert autopilot.run_once(api(routes, calls), NOW, {}) == 0
    assert "POST /agent/controls/slot/claim" in calls


def test_a_retried_slot_accepts_no_new_cards() -> None:  # 6
    calls: list[str] = []
    assert autopilot.run_slot(api(_slot_routes([]), calls), {}, first_try=False) is None
    assert "GET /cards/queue" not in calls


@pytest.mark.parametrize(("target", "accepted"), [(2, 0), (3, 1), (1, 0)])
def test_cards_in_flight_count_toward_the_accept_target(target: int, accepted: int) -> None:  # 6
    calls: list[str] = []
    queue = [{"id": f"q{i}", "status": "proposed", "score": i} for i in range(5)]
    cards = [_card("c1", "publish"), _card("c2", "run_draft")]
    a = api(_slot_routes(cards, **{"GET /cards/queue": queue}), calls)
    assert autopilot.top_up_cards(a, target) == accepted
    assert sum(c.endswith("/decision") for c in calls) == accepted


def test_cards_mid_stage_count_as_in_flight() -> None:  # /agent/work hides wait cards
    calls: list[str] = []
    queue = [{"id": f"q{i}", "status": "proposed", "score": i} for i in range(5)]
    pipeline = {"counts": {}, "cards": [_card("c1", "wait"), _card("c2", "wait"),
                                        _card("c3", "none"), _card("c4", "close")]}  # fmt: skip
    routes = _slot_routes([], **{"GET /cards/queue": queue, "GET /agent/pipeline": pipeline})
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(f"{request.method} {request.url.path}")
        if request.url.path == "/agent/pipeline":
            seen.append(request.url.query.decode())
        body = routes.get((request.method, request.url.path), {})
        return httpx.Response(200, json=body)

    client = httpx.Client(base_url="https://api.test", transport=httpx.MockTransport(handler))
    assert autopilot.top_up_cards(autopilot.Api(client, sleep=lambda _s: None), 3) == 1
    assert "GET /agent/pipeline" in calls
    assert seen == ["limit=200"]


def test_a_tick_with_a_non_zero_exit_code_fails_the_slot(
    caplog: pytest.LogCaptureFixture,
) -> None:
    runs = {"running": None, "last": {"tick": {"ok": True, "result": {"exit_code": 2}}}}
    calls: list[str] = []
    sent: dict[str, object] = {}
    routes = _slot_routes([], **{"GET /agent/runs": runs})
    with caplog.at_level("INFO", logger="autopilot"):
        assert autopilot.run_once(api(routes, calls, sent), NOW, {}) == 1
    assert sent["/agent/controls/slot/finish"] == {"slot": "2026-11-15-06", "ok": False}
    assert "POST /agent/run/research" not in calls
    lines = [r for r in caplog.records if r.message == "slot outcome"]
    assert lines[-1].reason == "tick exit_code 2"  # type: ignore[attr-defined]


def test_a_pause_mid_run_releases_the_slot_and_does_not_alert(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    alerts: list[str] = []
    monkeypatch.setattr(autopilot, "send_alert", lambda *a: alerts.append(a[1]))
    calls: list[str] = []
    sent: dict[str, object] = {}
    claim = {"claimed": True, "slot": "s", "failures": 2}
    routes = _slot_routes([], **{"POST /agent/run/tick": 423,
                                 "POST /agent/controls/slot/claim": claim})  # fmt: skip
    env = {"ALERT_WEBHOOK_URL": "https://hook.test"}
    assert autopilot.run_once(api(routes, calls, sent), NOW, env) == 0
    assert sent["/agent/controls/slot/finish"] == {
        "slot": "2026-11-15-06", "ok": False, "release": True,
    }  # fmt: skip
    assert alerts == []


def test_start_waits_and_retries_once_when_another_run_is_going() -> None:  # 7
    replies = iter([httpx.Response(409, json={}), httpx.Response(202, json={"started": True})])

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/agent/runs":
            return httpx.Response(200, json=ALL_OK)
        return next(replies)

    client = httpx.Client(base_url="https://api.test", transport=httpx.MockTransport(handler))
    assert autopilot.Api(client, sleep=lambda _s: None).start("tick") is True


@pytest.mark.parametrize("last", [{"tick": {"ok": False, "error": "KeyError"}}, {}])
def test_start_is_false_when_the_stage_did_not_end_ok(last: dict[str, object]) -> None:  # 9
    routes = {
        ("POST", "/agent/run/tick"): {"started": True},
        ("GET", "/agent/runs"): {"running": None, "last": last},
    }
    assert api(routes, []).start("tick") is False


def test_each_run_logs_one_outcome_line(caplog: pytest.LogCaptureFixture) -> None:  # 9
    caplog.set_level("INFO", logger="autopilot")
    routes = _slot_routes([], **{"GET /agent/runs": {"running": None, "last": {}}})
    assert autopilot.run_once(api(routes, []), NOW, {}) == 1
    lines = [r for r in caplog.records if hasattr(r, "outcome")]
    assert [(r.slot, r.outcome, r.reason) for r in lines] == [("2026-11-15-06", "failed", "tick")]  # type: ignore[attr-defined]


def test_claim_asks_for_a_lease_longer_than_a_slot_can_run() -> None:  # 11
    sent: dict[str, object] = {}
    routes = _slot_routes(
        [], **{"POST /agent/controls/slot/claim": {"claimed": False, "slot": "s", "failures": 0}}
    )
    autopilot.run_once(api(routes, [], sent), NOW, {})
    assert sent["/agent/controls/slot/claim"] == {"slot": "2026-11-15-06", "lease_minutes": 360}


def _images_env(tmp: object, monkeypatch: pytest.MonkeyPatch, script: bool) -> None:
    from pathlib import Path

    root = Path(str(tmp))
    if script:
        path = root / "skills" / "article-images" / "scripts" / "articleimg.py"
        path.parent.mkdir(parents=True)
        path.write_text("")
    monkeypatch.setattr(autopilot, "REPO", root)


def test_images_tick_warns_when_the_script_is_missing(
    tmp_path: object, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:  # 10
    _images_env(tmp_path, monkeypatch, script=False)
    monkeypatch.setattr("subprocess.run", lambda *_a, **_k: pytest.fail("ran"))
    autopilot.images_tick({"SIGNALFORGE_KEY": "k"})
    assert any("missing" in r.getMessage() for r in caplog.records if r.levelname == "WARNING")


def test_images_tick_logs_a_failed_exit_and_strips_secrets_from_the_child(
    tmp_path: object, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:  # 10, 14
    import subprocess

    _images_env(tmp_path, monkeypatch, script=True)
    for name in ("DATABASE_URL", "LLM_API_KEY", "TAVILY_API_KEY", "SUPABASE_SECRET_KEY"):
        monkeypatch.setenv(name, "secret-value")
    seen: dict[str, str] = {}

    def fake_run(*_a: object, env: dict[str, str], **_k: object) -> object:
        seen.update(env)
        return subprocess.CompletedProcess([], 3, stdout="OK a\nSKIP b: no figure\n", stderr="")

    monkeypatch.setattr("subprocess.run", fake_run)
    autopilot.images_tick({"SIGNALFORGE_KEY": "agent-key"})
    assert seen["EDITOR_API_KEY"] == "agent-key"
    assert not {"DATABASE_URL", "LLM_API_KEY", "TAVILY_API_KEY", "SUPABASE_SECRET_KEY"} & set(seen)
    warning = [r.getMessage() for r in caplog.records if r.levelname == "WARNING"]
    assert any("3" in m and "SKIP b: no figure" in m for m in warning)
    assert not any("secret-value" in m or "agent-key" in m for m in warning)
