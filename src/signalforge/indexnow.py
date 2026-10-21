"""IndexNow ping for newly published articles. Best effort: a failure never blocks publishing."""

import logging

import httpx

log = logging.getLogger(__name__)

INDEXNOW_ENDPOINT = "https://api.indexnow.org/indexnow"
_TIMEOUT_SECONDS = 10.0


def ping_indexnow(site_url: str, key: str, slug: str) -> bool:
    """Submit one article URL. Returns True when the endpoint accepted it (200 or 202)."""
    base = site_url.rstrip("/")
    if not base or not key:
        return False
    host = base.split("://", 1)[-1].split("/", 1)[0]
    body = {
        "host": host,
        "key": key,
        "keyLocation": f"{base}/indexnow-key.txt",
        "urlList": [f"{base}/articles/{slug}"],
    }
    try:
        response = httpx.post(INDEXNOW_ENDPOINT, json=body, timeout=_TIMEOUT_SECONDS)
    except httpx.HTTPError:
        log.warning("indexnow ping failed for %s", slug, exc_info=True)
        return False
    if response.status_code not in (200, 202):
        log.warning("indexnow rejected %s: status=%s", slug, response.status_code)
        return False
    return True
