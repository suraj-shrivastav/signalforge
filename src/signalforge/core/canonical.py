"""URL canonicalisation and content hashing for signals.

``canonical_url`` is the dedupe key: two signals about the same page must map to
the same string, otherwise the same event is researched twice (PRD §12).
"""

import hashlib
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from signalforge.core.errors import ArtifactValidationError

_DEFAULT_PORTS = {"http": 80, "https": 443}
# Tracking parameters carry no meaning about the page. utm_* is matched by prefix.
_TRACKING_PARAMS = frozenset({"fbclid", "gclid", "ref", "ref_src", "mc_cid", "mc_eid"})


def canonical_url(url: str) -> str:
    """Return a stable form of an http(s) URL.

    Lowercases scheme and host, drops credentials, default ports, fragments,
    tracking parameters and a trailing slash, and sorts the query string.

    Raises:
        ArtifactValidationError: if ``url`` is not an absolute http(s) URL.
    """
    parts = urlsplit(url.strip())
    scheme = parts.scheme.lower()
    try:
        host, port = parts.hostname, parts.port
    except ValueError as exc:
        raise ArtifactValidationError("Invalid URL", context={"url": url}) from exc
    if scheme not in _DEFAULT_PORTS or not host:
        raise ArtifactValidationError("Not an absolute http(s) URL", context={"url": url})

    netloc = host if port in (None, _DEFAULT_PORTS[scheme]) else f"{host}:{port}"
    query = urlencode(
        sorted(
            (key, value)
            for key, value in parse_qsl(parts.query, keep_blank_values=True)
            if not key.lower().startswith("utm_") and key.lower() not in _TRACKING_PARAMS
        )
    )
    return urlunsplit((scheme, netloc, parts.path.rstrip("/"), query, ""))


def content_hash(title: str, summary: str) -> str:
    """Hash of the normalised text, so a re-titled duplicate can be detected later."""
    normalised = "\n".join(" ".join(text.split()).casefold() for text in (title, summary))
    return hashlib.sha256(normalised.encode()).hexdigest()
