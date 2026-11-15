"""One best-effort alert channel: a Slack- or Discord-compatible incoming webhook."""

import logging

import httpx

log = logging.getLogger(__name__)
_TIMEOUT_S = 10.0


def send_alert(
    url: str | None, title: str, detail: str, *, client: httpx.Client | None = None
) -> bool:
    """POST the alert. Never raises: an alert must not break the run that sends it."""
    if not url:
        log.warning("alert not sent, ALERT_WEBHOOK_URL unset", extra={"title": title})
        return False
    text = f"[SignalForge] {title}: {detail}"
    http = client or httpx.Client(timeout=_TIMEOUT_S)
    try:
        response = http.post(url, json={"text": text, "content": text})
        ok = response.is_success
    except httpx.HTTPError as exc:
        log.warning("alert failed", extra={"title": title, "error": type(exc).__name__})
        return False
    finally:
        if client is None:
            http.close()
    if not ok:
        log.warning("alert rejected", extra={"title": title, "status": response.status_code})
    return ok
