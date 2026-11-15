"""Tell the web app to drop its cached article pages. Best effort: never raises.

The web app caches the article list and pages for up to five minutes
(``REVALIDATE_S`` in ``apps/web/src/lib/public.ts``). ``POST {SITE_URL}/api/revalidate`` with
the shared secret expires that cache, so a publish, an unpublish or new images show at once.
"""

import logging

import httpx

log = logging.getLogger(__name__)

_TIMEOUT_SECONDS = 10.0


def revalidate_site(site_url: str, secret: str) -> bool:
    """Expire the web cache. Returns True when the web app accepted the call (200)."""
    base = site_url.rstrip("/")
    if not base or not secret:
        return False
    try:
        response = httpx.post(
            f"{base}/api/revalidate",
            headers={"x-revalidate-secret": secret},
            timeout=_TIMEOUT_SECONDS,
        )
    except httpx.HTTPError as exc:
        log.warning("site revalidate failed: %s", type(exc).__name__)
        return False
    if response.status_code != 200:
        log.warning("site revalidate rejected: status=%s", response.status_code)
        return False
    return True
