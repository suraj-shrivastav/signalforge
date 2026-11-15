"""Autopilot: what the laptop's launchd scripts did, run by a cloud cron every 15 minutes.

    uv run python -m apps.worker.autopilot

It holds only the agent key and talks to the API; slot state and the kill switch live in
pipeline_controls, so any host can run it and two overlapping runs cannot both take a slot.
"""

import logging
import os
import subprocess
import sys
import time
import traceback
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from signalforge.alerts import send_alert
from signalforge.control_policy import slot_id
from signalforge.core.logging import configure_logging
from signalforge.pipeline_state import CLOSE_REASON_TAG

log = logging.getLogger("autopilot")
REPO = Path(__file__).resolve().parents[2]
_POLL_S = 60
_MAX_POLLS = 30
_LEASE_MINUTES = 360  # a worst-case slot runs about 330 min; the default lease is 120
# Cards that already hold a place in the pipeline: they count toward the accept target.
_IN_FLIGHT = ("run_research", "retry_research", "run_draft", "retry_draft", "auto_review",
              "run_revise", "publish")  # fmt: skip


class PausedError(Exception):
    """The API answered 423: stop this run cleanly."""


class Api:
    def __init__(self, client: httpx.Client, sleep: Callable[[float], None] = time.sleep) -> None:
        self._client = client
        self._sleep = sleep

    def call(self, method: str, path: str, **kw: Any) -> Any:
        for attempt in range(4):
            try:
                response = self._client.request(method, path, **kw)
            except httpx.HTTPError as exc:
                log.warning("%s %s failed: %s", method, path, type(exc).__name__)
                self._sleep(20)
                continue
            if response.status_code == 423:
                raise PausedError(path)
            if response.status_code >= 500 and attempt < 3:
                self._sleep(20)
                continue
            response.raise_for_status()
            return response.json() if response.content else {}
        raise RuntimeError(f"{method} {path} failed after retries")

    def wait_stage(self, name: str, polls: int = _MAX_POLLS) -> dict[str, Any] | None:
        """The /agent/runs body once no run is going. None: still running or unknown."""
        for _ in range(polls):
            try:
                response = self._client.get("/agent/runs")
                body = response.json() if response.is_success else None
            except (httpx.HTTPError, ValueError):
                body = None
            if isinstance(body, dict) and not body.get("running"):
                return body
            self._sleep(_POLL_S)
        log.warning("%s still running or unknown after %d polls", name, polls)
        return None

    def start(self, stage: str, **params: Any) -> bool:
        """Run ``stage`` and wait for it. True only if /agent/runs says it ended ok."""
        path = f"/agent/run/{stage}"
        try:
            body = self.call("POST", path, params=params)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code != 409:
                raise
            log.info("%s: another run is going, waiting for it", stage)  # 409: retry once
            if self.wait_stage(stage) is None:
                return False
            body = self.call("POST", path, params=params)
        runs = self.wait_stage(stage) if body.get("started") else None
        last = (runs or {}).get("last", {}).get(stage)
        if runs is None or not isinstance(last, dict) or not last.get("ok"):
            error = last.get("error") if isinstance(last, dict) else "no result"
            log.warning("%s did not finish ok: %s", stage, error)  # error is a type name
            return False
        if stage == "tick" and (last.get("result") or {}).get("exit_code"):
            log.warning("tick exited %s", last["result"]["exit_code"])
        return True


def current_slot(now: datetime, tz: str) -> str:
    return slot_id(now.astimezone(ZoneInfo(tz)))


def revalidate_site(env: Mapping[str, str]) -> None:
    site, secret = env.get("SITE_URL"), env.get("REVALIDATE_SECRET")
    if not (site and secret):
        return
    try:
        httpx.post(
            f"{site.rstrip('/')}/api/revalidate",
            headers={"x-revalidate-secret": secret},
            timeout=30,
        )
    except httpx.HTTPError:
        log.warning("site revalidate failed")


def publish_tick(api: Api, env: Mapping[str, str]) -> None:
    body = api.call("POST", "/agent/publish-next")
    if isinstance(body.get("published"), dict):
        log.info("published %s", body["published"].get("slug"))
        revalidate_site(env)


def images_tick(env: Mapping[str, str]) -> None:
    if not env.get("SIGNALFORGE_KEY"):  # unit tests pass env={}; never spawn the script there
        return
    script = REPO / "skills" / "article-images" / "scripts" / "articleimg.py"
    if not script.exists():
        log.warning("images tick skipped: %s is missing", script.relative_to(REPO))
        return
    child = {k: v for k, v in {**os.environ, **env}.items() if not _withheld(k)}
    child.setdefault("EDITOR_API_KEY", env["SIGNALFORGE_KEY"])  # articleimg reads this name
    try:
        out = subprocess.run(
            [sys.executable, str(script), "auto"],
            env=child, capture_output=True, text=True, timeout=600, check=False,
        )  # fmt: skip
    except (OSError, subprocess.TimeoutExpired) as exc:
        log.warning("images tick failed: %s", type(exc).__name__)
        return
    if out.returncode != 0:
        tail = out.stdout.strip().splitlines()[-1:]
        log.warning("images tick exited %d: %s", out.returncode, tail[0] if tail else "")
    if any(line.startswith("OK ") for line in out.stdout.splitlines()):
        revalidate_site(env)


def _withheld(name: str) -> bool:
    """Credentials the image script never needs: it gets only the agent key."""
    return (
        name.startswith("SUPABASE_")
        or name == "DATABASE_URL"
        or (name.endswith("_API_KEY") and name != "EDITOR_API_KEY")
    )


def close_dead_ends(api: Api) -> int:
    closed = 0
    for card in api.call("GET", "/agent/work").get("cards", []):
        if card.get("next_action") != "close":
            continue
        api.call(
            "POST", f"/cards/{card['card_id']}/decision",
            json={"decision": "rejected", "reason_tags": [CLOSE_REASON_TAG],
                  "note": f"auto-closed: {card['stage']}"},
        )  # fmt: skip
        log.info("auto-closed %s (%s): %s", card["card_id"], card["stage"], card.get("title"))
        closed += 1
    return closed


def _work(api: Api, action: str) -> list[dict[str, Any]]:
    return [
        c for c in api.call("GET", "/agent/work").get("cards", []) if c["next_action"] == action
    ]


def accept_best_cards(api: Api, count: int) -> int:
    if count <= 0:
        return 0
    queue = api.call("GET", "/cards/queue", params={"limit": 50})
    proposed = [i for i in queue if i.get("status") == "proposed"]  # /cards/queue: list[CardOut]
    proposed.sort(key=lambda i: i.get("score") or 0, reverse=True)
    for item in proposed[:count]:
        api.call(
            "POST", f"/cards/{item['id']}/decision",
            json={"decision": "accepted", "note": "auto-accepted: topmost by score"},
        )  # fmt: skip
    return min(count, len(proposed))


def top_up_cards(api: Api, target: int) -> int:
    """Accept just enough cards that about ``target`` are in flight (publish queue included)."""
    cards = api.call("GET", "/agent/work").get("cards", [])
    in_flight = sum(1 for c in cards if c.get("next_action") in _IN_FLIGHT)
    return accept_best_cards(api, max(0, target - in_flight))


def _accept_target(env: Mapping[str, str]) -> int:
    try:
        return max(0, int(env.get("AUTOPILOT_ACCEPT_PER_RUN", "2")))
    except ValueError:
        log.warning("AUTOPILOT_ACCEPT_PER_RUN is not a whole number, using 2")
        return 2


def review_cards(api: Api, env: Mapping[str, str]) -> None:
    for card in _work(api, "auto_review")[:3]:
        for attempt in range(3):
            path = f"/agent/drafts/{card['card_id']}/auto-review"
            try:
                body = api.call("POST", path, params={"publish": "true"})
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code != 409:
                    raise
                log.info("auto-review skipped %s: no longer pending", card["card_id"])
                break
            if isinstance(body.get("published"), dict):
                revalidate_site(env)
            if body.get("action") != "revise" or attempt == 2 or not api.start("revise"):
                break


def run_slot(api: Api, env: Mapping[str, str], first_try: bool) -> str | None:
    """Run one slot. None when it finished, else the step that failed."""
    if not api.start("tick"):
        return "tick"
    if first_try:  # a retried slot already accepted its cards
        top_up_cards(api, _accept_target(env))
    for _ in range(2):
        waiting = len(_work(api, "run_research")) + len(_work(api, "retry_research"))
        if not api.start("research", retry_failed="true", limit=max(1, min(4, waiting))):
            return "research"
        if not api.start("draft", retry_failed="true"):
            return "draft"
        if _work(api, "auto_review"):
            break
    if _work(api, "run_revise") and not api.start("revise"):
        return "revise"
    review_cards(api, env)
    publish_tick(api, env)
    return None


def _why(exc: BaseException) -> str:
    """Type and place, or HTTP status and path: never the message, which can carry a URL."""
    if isinstance(exc, httpx.HTTPStatusError):
        return f"HTTP {exc.response.status_code} {exc.request.url.path}"
    frames = traceback.extract_tb(exc.__traceback__)[-1:]
    return type(exc).__name__ + "".join(f" at {f.name}:{f.lineno}" for f in frames)


def _outcome(slot: str, outcome: str, reason: str | None, code: int) -> int:
    log.info("slot outcome", extra={"slot": slot, "outcome": outcome, "reason": reason})
    return code


def _finish(api: Api, env: Mapping[str, str], slot: str, ok: bool, failures: int | None) -> None:
    """Close the claimed slot. ``failures`` None (a pause) never alerts."""
    try:
        api.call("POST", "/agent/controls/slot/finish", json={"slot": slot, "ok": ok})
    except Exception as exc:  # noqa: BLE001 - the alert below must still go out
        log.warning("slot finish failed: %s", _why(exc))
    if not ok and failures is not None and failures + 1 >= 3:
        send_alert(env.get("ALERT_WEBHOOK_URL"), "slot failed 3 times", slot)  # never raises


def run_once(api: Api, now: datetime, env: Mapping[str, str]) -> int:
    slot = current_slot(now, env.get("AUTOPILOT_TZ", "UTC"))
    try:
        paused = api.call("GET", "/agent/controls").get("paused")
    except Exception as exc:  # noqa: BLE001
        return _outcome(slot, "failed", f"controls: {_why(exc)}", 1)
    if paused:
        return _outcome(slot, "paused", "paused before the run", 0)
    try:
        steps = (("publish", lambda: publish_tick(api, env)), ("images", lambda: images_tick(env)),
                 ("close", lambda: close_dead_ends(api)))  # fmt: skip
        for name, step in steps:  # each is best effort: none may keep the slot from running
            try:
                step()
            except PausedError:
                raise
            except Exception as exc:  # noqa: BLE001
                log.warning("%s step failed: %s", name, _why(exc))
        body = {"slot": slot, "lease_minutes": _LEASE_MINUTES}
        claim = api.call("POST", "/agent/controls/slot/claim", json=body)
    except PausedError:
        return _outcome(slot, "paused", "paused before the claim", 0)
    except Exception as exc:  # noqa: BLE001
        return _outcome(slot, "failed", f"claim: {_why(exc)}", 1)
    if not claim.get("claimed"):
        return _outcome(slot, "skipped", "slot held or done", 0)
    failures = int(claim.get("failures", 0))
    try:
        failed = run_slot(api, env, first_try=failures == 0)
    except PausedError:
        _finish(api, env, slot, False, None)
        return _outcome(slot, "paused", "paused mid-run", 0)
    except Exception as exc:  # noqa: BLE001 - finish the slot so the failure counts
        failed = _why(exc)
    _finish(api, env, slot, failed is None, failures)
    if failed is None:
        return _outcome(slot, "done", None, 0)
    return _outcome(slot, "failed", failed, 1)


def main() -> int:
    configure_logging("INFO")
    env = dict(os.environ)
    base, key = env.get("API_BASE_URL"), env.get("SIGNALFORGE_KEY")
    if not (base and key):
        log.error("API_BASE_URL and SIGNALFORGE_KEY are required")
        return 1
    client = httpx.Client(base_url=base, headers={"X-Editor-Key": key}, timeout=180)
    with client:
        return run_once(Api(client), datetime.now(UTC), env)


if __name__ == "__main__":
    raise SystemExit(main())
