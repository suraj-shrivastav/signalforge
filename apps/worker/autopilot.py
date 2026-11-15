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

    def wait_stage(self, name: str, polls: int = _MAX_POLLS) -> bool:
        """True once no run is going. A failed or odd reply means unknown, never finished."""
        for _ in range(polls):
            try:
                response = self._client.get("/agent/runs")
                body = response.json() if response.is_success else None
            except (httpx.HTTPError, ValueError):
                body = None
            if isinstance(body, dict) and not body.get("running"):
                return True
            self._sleep(_POLL_S)
        log.warning("%s still running or unknown after %d polls", name, polls)
        return False

    def start(self, stage: str, **params: Any) -> bool:
        body = self.call("POST", f"/agent/run/{stage}", params=params)
        return bool(body.get("started")) and self.wait_stage(stage)


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
    child = {k: v for k, v in {**os.environ, **env}.items() if not k.startswith("SUPABASE_")}
    child.setdefault("EDITOR_API_KEY", env["SIGNALFORGE_KEY"])  # articleimg reads this name
    try:
        out = subprocess.run(
            [sys.executable, str(script), "auto"],
            env=child, capture_output=True, text=True, timeout=600, check=False,
        )  # fmt: skip
    except (OSError, subprocess.TimeoutExpired) as exc:
        log.warning("images tick failed: %s", type(exc).__name__)
        return
    if any(line.startswith("OK ") for line in out.stdout.splitlines()):
        revalidate_site(env)


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
        closed += 1
    return closed


def _work(api: Api, action: str) -> list[dict[str, Any]]:
    return [
        c for c in api.call("GET", "/agent/work").get("cards", []) if c["next_action"] == action
    ]


def accept_best_cards(api: Api, count: int) -> int:
    queue = api.call("GET", "/cards/queue", params={"limit": 50})
    proposed = [i for i in queue if i.get("status") == "proposed"]  # /cards/queue: list[CardOut]
    proposed.sort(key=lambda i: i.get("score") or 0, reverse=True)
    for item in proposed[:count]:
        api.call(
            "POST", f"/cards/{item['id']}/decision",
            json={"decision": "accepted", "note": "auto-accepted: topmost by score"},
        )  # fmt: skip
    return min(count, len(proposed))


def review_cards(api: Api, env: Mapping[str, str]) -> None:
    for card in _work(api, "auto_review")[:3]:
        for attempt in range(3):
            body = api.call(
                "POST", f"/agent/drafts/{card['card_id']}/auto-review", params={"publish": "true"}
            )
            if isinstance(body.get("published"), dict):
                revalidate_site(env)
            if body.get("action") != "revise" or attempt == 2 or not api.start("revise"):
                break


def run_slot(api: Api, env: Mapping[str, str]) -> bool:
    if not api.start("tick"):
        return False
    accept_best_cards(api, int(env.get("AUTOPILOT_ACCEPT_PER_RUN", "2")))
    for _ in range(2):
        waiting = len(_work(api, "run_research")) + len(_work(api, "retry_research"))
        if not api.start("research", retry_failed="true", limit=max(1, min(4, waiting))):
            return False
        if not api.start("draft", retry_failed="true"):
            return False
        if _work(api, "auto_review"):
            break
    review_cards(api, env)
    publish_tick(api, env)
    return True


def run_once(api: Api, now: datetime, env: Mapping[str, str]) -> int:
    if api.call("GET", "/agent/controls").get("paused"):
        log.info("paused, nothing to do")
        return 0
    slot = current_slot(now, env.get("AUTOPILOT_TZ", "UTC"))
    claim: dict[str, Any] = {}
    try:
        publish_tick(api, env)
        images_tick(env)
        close_dead_ends(api)
        claim = api.call("POST", "/agent/controls/slot/claim", json={"slot": slot})
        if not claim.get("claimed"):
            return 0
        ok = run_slot(api, env)
    except PausedError:
        log.info("paused mid-run")
        if claim.get("claimed"):  # never finish a slot another run holds
            api.call("POST", "/agent/controls/slot/finish", json={"slot": slot, "ok": False})
        return 0
    except (httpx.HTTPError, RuntimeError):
        log.exception("slot %s aborted", slot)
        ok = False
        if not claim.get("claimed"):
            return 1
    api.call("POST", "/agent/controls/slot/finish", json={"slot": slot, "ok": ok})
    if not ok and claim.get("failures", 0) + 1 >= 3:
        send_alert(env.get("ALERT_WEBHOOK_URL"), "slot failed 3 times", slot)
    return 0 if ok else 1


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
