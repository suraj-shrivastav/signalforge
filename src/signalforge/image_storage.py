"""Upload article images to the public Supabase bucket on behalf of an agent.

The agent renders the SVG; the API holds the Supabase secret, so the secret never leaves it.
"""

import hashlib
import logging
import re

import httpx

log = logging.getLogger(__name__)

BUCKET = "article-images"
MAX_SVG_BYTES = 300_000
_TIMEOUT_SECONDS = 30.0
_UNSAFE = re.compile(
    r"<\s*(script|foreignObject|iframe|object|embed|image|use)\b|\son\w+\s*=|javascript:",
    re.IGNORECASE,
)


class ImageStorageError(Exception):
    """The image was refused or the storage call failed. ``message`` is safe to show."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


def check_svg(svg: str) -> None:
    """Refuse anything that is not a plain, self-contained SVG."""
    if len(svg.encode()) > MAX_SVG_BYTES:
        raise ImageStorageError("SVG is larger than 300 KB")
    if not svg.lstrip().startswith(("<svg", "<?xml")) or "</svg>" not in svg:
        raise ImageStorageError("Not an SVG document")
    if _UNSAFE.search(svg):
        raise ImageStorageError("SVG contains scripts, embedded content or event handlers")


def _headers(key: str, content_type: str | None = None) -> dict[str, str]:
    headers = {"apikey": key}
    if not key.startswith("sb_"):  # legacy JWT keys also go in Authorization
        headers["Authorization"] = f"Bearer {key}"
    if content_type:
        headers["Content-Type"] = content_type
    return headers


def upload_svg(svg: str, *, slug: str, role: str, supabase_url: str, key: str) -> str:
    """Store one SVG and return its public URL."""
    check_svg(svg)
    base = supabase_url.rstrip("/")
    try:
        # 400 and 409 mean the bucket already exists.
        bucket = httpx.post(
            f"{base}/storage/v1/bucket",
            headers=_headers(key, "application/json"),
            json={"id": BUCKET, "name": BUCKET, "public": True},
            timeout=_TIMEOUT_SECONDS,
        )
        if bucket.status_code not in (200, 201, 400, 409):
            raise ImageStorageError(f"Storage refused the bucket check ({bucket.status_code})")
        digest = hashlib.sha256(svg.encode()).hexdigest()[:8]
        path = f"{slug}/{role}-{digest}.svg"
        response = httpx.post(
            f"{base}/storage/v1/object/{BUCKET}/{path}",
            headers={
                **_headers(key, "image/svg+xml"),
                "x-upsert": "true",
                "cache-control": "max-age=31536000",
            },
            content=svg.encode(),
            timeout=_TIMEOUT_SECONDS,
        )
    except httpx.HTTPError as exc:
        log.warning("image upload failed for %s", slug, exc_info=True)
        raise ImageStorageError("Storage is unreachable") from exc
    if response.status_code not in (200, 201):
        log.warning("image upload rejected for %s: status=%s", slug, response.status_code)
        raise ImageStorageError(f"Storage rejected the upload ({response.status_code})")
    return f"{base}/storage/v1/object/public/{BUCKET}/{path}"
