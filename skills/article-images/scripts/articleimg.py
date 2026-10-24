#!/usr/bin/env python3
"""Article image tool: validate a spec, render an SVG, upload it, attach it to an article.

Standard library only. The agent never writes SVG: it writes a small JSON spec and this
script checks it against the article, draws it, and publishes it.

    articleimg.py validate SPEC.json --slug SLUG
    articleimg.py render   SPEC.json --slug SLUG --out FILE.svg
    articleimg.py publish  --slug SLUG --cover COVER.json --figure FIGURE.json [--dry-run DIR]

Environment for publish: API_BASE_URL, EDITOR_API_KEY, SUPABASE_URL, SUPABASE_SECRET_KEY.
"""

import argparse
import hashlib
import json
import math
import os
import random
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

W, H = 1200, 900
INK = "#14201a"
WHITE = "#ffffff"
PALETTE = ["#f4c9cc", "#f6e0a4", "#bfe0d2", "#c3d5ef", "#dccdef"]  # rose, butter, mint, sky, lilac
FONT = "'Bricolage Grotesque','Helvetica Neue',Arial,sans-serif"
BUCKET = "article-images"
TEMPLATES = (
    "waveform",
    "figure-ripples",
    "compare-blocks",
    "constellation",
    "spectrogram",
    "layers",
)
ROLES = ("cover", "figure")
LIMITS = {
    "label": 28,
    "figure": 8,
    "caption": 34,
    "alt": 140,
    "name": 14,
    "text": 8,
    "item": 30,
    "word": 6,
}
NUMBER = re.compile(r"\d[\d.,]*")


class SpecError(Exception):
    pass


# ---------------------------------------------------------------- validation


def _num_tokens(text: str) -> set[str]:
    return {m.group(0).rstrip(".,").replace(",", "") for m in NUMBER.finditer(text)}


def article_text(article: dict[str, Any]) -> str:
    """Text a number may be taken from: title, dek and the verified or supported claims."""
    claims = [
        c["text"] for c in article.get("claims", []) if c.get("status") in ("verified", "supported")
    ]
    return " ".join([article.get("title", ""), article.get("dek", ""), *claims])


def _text(spec: dict[str, Any], key: str, errors: list[str], *, required: bool = True) -> str:
    value = spec.get(key)
    if value is None or value == "":
        if required:
            errors.append(f"{key}: required")
        return ""
    if not isinstance(value, str):
        errors.append(f"{key}: must be a string")
        return ""
    limit = LIMITS.get(key, 99)
    if len(value) > limit:
        errors.append(f"{key}: {len(value)} characters, limit {limit}")
    return value


def validate(spec: dict[str, Any], article: dict[str, Any] | None) -> list[str]:
    """Return every problem found. Empty list means the spec is valid."""
    errors: list[str] = []
    allowed = {"role", "template", "label", "alt", "figure", "caption", "values"}
    extra = set(spec) - allowed
    if extra:
        errors.append(f"unknown fields: {sorted(extra)}")
    if spec.get("role") not in ROLES:
        errors.append(f"role: must be one of {list(ROLES)}")
    template = spec.get("template")
    if template not in TEMPLATES:
        errors.append(f"template: must be one of {list(TEMPLATES)}")
        return errors
    texts: list[str] = [_text(spec, "label", errors)]
    _text(spec, "alt", errors)
    values = spec.get("values", {})
    if not isinstance(values, dict):
        errors.append("values: must be an object")
        return errors
    if template in ("waveform", "figure-ripples", "constellation"):
        texts += [_text(spec, "figure", errors), _text(spec, "caption", errors)]
        if template == "constellation":
            count = values.get("count")
            if not isinstance(count, int) or not 3 <= count <= 9:
                errors.append("values.count: integer 3 to 9")
    elif template == "spectrogram":
        texts += [_text(spec, "figure", errors), _text(spec, "caption", errors, required=False)]
        if len(spec.get("figure", "")) > LIMITS["word"]:
            errors.append(f"figure: spectrogram word is at most {LIMITS['word']} characters")
    elif template == "compare-blocks":
        for side in ("a", "b"):
            block = values.get(side)
            if not isinstance(block, dict):
                errors.append(f"values.{side}: object with value, text, name")
                continue
            if not isinstance(block.get("value"), (int, float)) or block["value"] <= 0:
                errors.append(f"values.{side}.value: positive number (used for block size)")
            texts += [_text(block, "text", errors), _text(block, "name", errors)]
        if "figure" in spec or "caption" in spec:
            errors.append("compare-blocks takes no figure or caption; use values.a and values.b")
    elif template == "layers":
        items = values.get("items")
        if not isinstance(items, list) or len(items) != 3:
            errors.append("values.items: exactly 3 strings")
        else:
            for item in items:
                if not isinstance(item, str) or not item or len(item) > LIMITS["item"]:
                    errors.append(f"values.items: each 1 to {LIMITS['item']} characters")
                else:
                    texts.append(item)
        if "figure" in spec or "caption" in spec:
            errors.append("layers takes no figure or caption; use values.items")
    if article is not None:
        source = _num_tokens(article_text(article))
        for token in sorted(set().union(*(_num_tokens(t) for t in texts if t))):
            if token not in source:
                errors.append(
                    f"number {token!r} is not in the article's title, dek or verified claims"
                )
    return errors


def check_pair(cover: dict[str, Any], figure: dict[str, Any]) -> list[str]:
    errors = []
    if cover.get("role") != "cover" or figure.get("role") != "figure":
        errors.append("first spec must have role cover, second role figure")
    if cover.get("template") == figure.get("template"):
        errors.append("cover and figure must use different templates")
    return errors


# ---------------------------------------------------------------- drawing


class Seed:
    """Deterministic variation from the slug: same article, same images; other articles differ."""

    def __init__(self, slug: str, role: str) -> None:
        digest = hashlib.sha256(f"{slug}|{role}".encode()).digest()
        self.n = int.from_bytes(digest[:8], "big")
        self.rng = random.Random(self.n)
        self.palette = (digest[0] + (2 if role == "figure" else 0)) % len(PALETTE)

    def pick(self, options: list[Any]) -> Any:
        return options[self.rng.randrange(len(options))]


def esc(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def fit(text: str, max_width: float, max_size: float, factor: float = 0.62) -> int:
    """Largest font size at which `text` fits `max_width` (heavy sans: ~0.62 em per glyph)."""
    return int(min(max_size, max_width / (factor * max(len(text), 1))))


def txt(
    x: float,
    y: float,
    text: str,
    size: float,
    *,
    weight: int = 800,
    fill: str = INK,
    opacity: float = 1,
    spacing: float = -0.04,
    anchor: str = "start",
) -> str:
    return (
        f'<text x="{x:.0f}" y="{y:.0f}" font-family="{FONT}" font-size="{size:.0f}" '
        f'font-weight="{weight}" letter-spacing="{spacing}em" fill="{fill}" opacity="{opacity}" '
        f'text-anchor="{anchor}">{esc(text)}</text>'
    )


def label(text: str) -> str:
    return txt(80, 110, text.upper(), 34, weight=600, opacity=0.7, spacing=0.08)


def wrap(spec: dict[str, Any], seed: Seed, body: str) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" role="img" '
        f'aria-label="{esc(spec["alt"])}"><title>{esc(spec["alt"])}</title>'
        f'<rect width="{W}" height="{H}" rx="56" fill="{PALETTE[seed.palette]}"/>{body}</svg>'
    )


def hero(spec: dict[str, Any], x: float, y: float, max_w: float, max_size: float) -> str:
    return txt(x, y, spec["figure"], fit(spec["figure"], max_w, max_size))


def caption(
    spec: dict[str, Any], x: float, y: float, size: float = 52, anchor: str = "start"
) -> str:
    if not spec.get("caption"):
        return ""
    return txt(
        x,
        y,
        spec["caption"],
        fit(spec["caption"], 1040 if anchor == "start" else 700, size, 0.56),
        weight=700,
        anchor=anchor,
    )


def draw_waveform(spec: dict[str, Any], seed: Seed) -> str:
    n = seed.pick([28, 30, 32, 34, 36])
    f1, f2 = seed.pick([0.45, 0.55, 0.65]), seed.pick([0.17, 0.21, 0.27])
    phase = seed.rng.random() * 6
    gap = 1040 / n
    bars = []
    for i in range(n):
        h = (
            50
            + abs(math.sin(i * f1 + phase) * math.cos(i * f2 + phase)) * 300
            + seed.rng.random() * 36
        )
        mid = n * seed.pick([0.3, 0.4, 0.5])
        strong = abs(i - mid) < n * 0.18
        bars.append(
            f'<rect x="{80 + i * gap:.0f}" y="{390 - h / 2:.0f}" width="{gap * 0.56:.0f}" '
            f'height="{h:.0f}" rx="{gap * 0.28:.0f}" fill="{INK}" '
            f'opacity="{0.9 if strong else 0.32}"/>'
        )
    return (
        label(spec["label"])
        + "".join(bars)
        + hero(spec, 76, 760, 1040, 230)
        + caption(spec, 80, 850, 44)
    )


def draw_ripples(spec: dict[str, Any], seed: Seed) -> str:
    cx, cy = seed.pick([900, 930, 960]), seed.pick([260, 330, 400])
    step = seed.pick([80, 90, 100])
    rings = "".join(
        f'<circle cx="{cx}" cy="{cy}" r="{step * (i + 1) + 50}" fill="none" stroke="{INK}" '
        f'stroke-width="3" opacity="{0.55 - i * 0.09:.2f}"/>'
        for i in range(5)
    )
    return (
        rings + label(spec["label"]) + hero(spec, 70, 640, 1040, 330) + caption(spec, 80, 780, 56)
    )


def draw_compare(spec: dict[str, Any], seed: Seed) -> str:
    a, b = spec["values"]["a"], spec["values"]["b"]
    big, small = (a, b) if a["value"] >= b["value"] else (b, a)
    ratio = math.sqrt(small["value"] / big["value"])  # area proportional to value
    big_s = 640
    small_s = max(190, min(640, int(big_s * ratio)))
    gap = 40
    room = 1040  # canvas width minus the 80px margins
    if big_s + gap + small_s > room:  # near-equal values: shrink both so the pair fits
        scale = (room - gap) / (big_s + small_s)
        big_s, small_s = int(big_s * scale), int(small_s * scale)
    first, second = ((big, big_s, True), (small, small_s, False))
    if seed.pick([False, True]):
        first, second = second, first
    x_first = 80
    x_second = x_first + first[1] + gap
    top = 190
    parts = [label(spec["label"])]
    for (blk, size, dark), x in ((first, x_first), (second, x_second)):
        y = top + 640 - size
        fill, ink = (INK, PALETTE[seed.palette]) if dark else (WHITE, INK)
        fs = fit(blk["text"], size - 60, 200 if dark else 120)
        parts.append(
            f'<rect x="{x}" y="{y}" width="{size}" height="{size}" '
            f'rx="{int(size * 0.1)}" fill="{fill}"/>'
        )
        parts.append(txt(x + 40, y + size - 90, blk["text"], fs, fill=ink))
        parts.append(
            txt(
                x + 42, y + size - 40, blk["name"], 34, weight=600, fill=ink, opacity=0.8, spacing=0
            )
        )
    return "".join(parts)


def draw_constellation(spec: dict[str, Any], seed: Seed) -> str:
    n = spec["values"]["count"]
    cx, cy = seed.pick([820, 850, 880]), seed.pick([440, 470])
    radius = seed.pick([250, 280, 300])
    rot = seed.rng.random() * math.tau
    pts = [
        (
            cx + radius * math.cos(rot + i * math.tau / n),
            cy + radius * math.sin(rot + i * math.tau / n),
        )
        for i in range(n)
    ]
    lines = "".join(
        f'<line x1="{cx}" y1="{cy}" x2="{x:.0f}" y2="{y:.0f}" '
        f'stroke="{INK}" stroke-width="3" opacity=".5"/>'
        for x, y in pts
    )
    nodes = "".join(
        f'<circle cx="{x:.0f}" cy="{y:.0f}" r="{seed.pick([30, 34, 38])}" fill="{INK}"/>'
        for x, y in pts
    )
    hub = f'<circle cx="{cx}" cy="{cy}" r="78" fill="{WHITE}" stroke="{INK}" stroke-width="6"/>'
    return (
        lines
        + nodes
        + hub
        + label(spec["label"])
        + hero(spec, 70, 700, 520, 520)
        + caption(spec, 80, 850, 44)
    )


def draw_spectrogram(spec: dict[str, Any], seed: Seed) -> str:
    cols, rows = 22, 11
    p1, p2 = seed.rng.random() * 6, seed.rng.random() * 6
    cells = []
    for c in range(cols):
        for r in range(rows):
            v = 0.5 + 0.5 * math.sin(c * 0.45 + r * 0.6 + p1) * math.cos(c * 0.13 + p2)
            v = max(0.0, min(1.0, v + seed.rng.uniform(-0.15, 0.15))) * (1 - r / rows * 0.5)
            cells.append(
                f'<rect x="{80 + c * 48}" y="{190 + r * 46}" width="40" height="38" rx="12" '
                f'fill="{INK}" opacity="{0.08 + v * 0.8:.2f}"/>'
            )
    return (
        label(spec["label"])
        + "".join(cells)
        + txt(76, 880, spec["figure"], fit(spec["figure"], 600, 130))
        + caption(spec, 1120, 870, 40, anchor="end")
    )


def draw_layers(spec: dict[str, Any], seed: Seed) -> str:
    items = spec["values"]["items"]
    widths = seed.pick([[900, 740, 560], [560, 740, 900], [740, 900, 560]])
    right = seed.pick([False, True])
    accent = PALETTE[(seed.palette + 1) % len(PALETTE)]
    fills = [(INK, PALETTE[seed.palette]), (WHITE, INK), (accent, INK)]
    parts = [label(spec["label"])]
    for i, (text, w) in enumerate(zip(items, widths, strict=True)):
        x = 1120 - w - 30 if right else 150
        y = 230 + i * 190
        fill, ink = fills[i]
        parts.append(f'<rect x="{x}" y="{y}" width="{w}" height="150" rx="75" fill="{fill}"/>')
        parts.append(
            txt(x + 60, y + 92, text, fit(text, w - 120, 46, 0.56), weight=700, fill=ink, spacing=0)
        )
    return "".join(parts)


DRAW = {
    "waveform": draw_waveform,
    "figure-ripples": draw_ripples,
    "compare-blocks": draw_compare,
    "constellation": draw_constellation,
    "spectrogram": draw_spectrogram,
    "layers": draw_layers,
}


def render(spec: dict[str, Any], slug: str) -> str:
    seed = Seed(slug, spec["role"])
    return wrap(spec, seed, DRAW[spec["template"]](spec, seed))


# ---------------------------------------------------------------- publishing


def _request(
    url: str,
    *,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    data: bytes | None = None,
) -> tuple[int, bytes]:
    req = urllib.request.Request(url, data=data, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()


def fetch_article(slug: str, api_base: str) -> dict[str, Any]:
    status, body = _request(f"{api_base.rstrip('/')}/articles/{slug}")
    if status != 200:
        raise SpecError(f"article {slug!r} not found or not published (HTTP {status})")
    return json.loads(body)


def _storage_headers(key: str, content_type: str | None = None) -> dict[str, str]:
    headers = {"apikey": key}
    if not key.startswith("sb_"):  # legacy JWT keys also go in Authorization
        headers["Authorization"] = f"Bearer {key}"
    if content_type:
        headers["Content-Type"] = content_type
    return headers


def upload(svg: str, slug: str, role: str, supabase_url: str, key: str) -> str:
    base = supabase_url.rstrip("/")
    status, body = _request(
        f"{base}/storage/v1/bucket",
        method="POST",
        headers=_storage_headers(key, "application/json"),
        data=json.dumps({"id": BUCKET, "name": BUCKET, "public": True}).encode(),
    )
    if status not in (200, 201, 400, 409):  # 400/409: bucket already exists
        raise SpecError(f"could not create bucket (HTTP {status})")
    digest = hashlib.sha256(svg.encode()).hexdigest()[:8]
    path = f"{slug}/{role}-{digest}.svg"
    headers = {
        **_storage_headers(key, "image/svg+xml"),
        "x-upsert": "true",
        "cache-control": "max-age=31536000",
    }
    status, body = _request(
        f"{base}/storage/v1/object/{BUCKET}/{path}",
        method="POST",
        headers=headers,
        data=svg.encode(),
    )
    if status not in (200, 201):
        raise SpecError(f"upload failed (HTTP {status}): {body[:200].decode(errors='replace')}")
    return f"{base}/storage/v1/object/public/{BUCKET}/{path}"


def attach(
    slug: str, cover: dict[str, str], figure: dict[str, str], api_base: str, editor_key: str
) -> None:
    status, body = _request(
        f"{api_base.rstrip('/')}/editor/articles/{slug}/images",
        method="POST",
        headers={"Content-Type": "application/json", "X-Editor-Key": editor_key},
        data=json.dumps({"cover": cover, "figure": figure}).encode(),
    )
    if status != 200:
        raise SpecError(f"attach failed (HTTP {status}): {body[:200].decode(errors='replace')}")


def _load(path: str) -> dict[str, Any]:
    return json.loads(Path(path).read_text())


def _env(name: str) -> str:
    value = os.environ.get(name, "")
    if not value:
        raise SpecError(f"environment variable {name} is not set")
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="articleimg")
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name in ("validate", "render"):
        p = sub.add_parser(name)
        p.add_argument("spec")
        p.add_argument("--slug", required=True)
        if name == "render":
            p.add_argument("--out", required=True)
    pub = sub.add_parser("publish")
    pub.add_argument("--slug", required=True)
    pub.add_argument("--cover", required=True)
    pub.add_argument("--figure", required=True)
    pub.add_argument("--dry-run", metavar="DIR", help="render into DIR, upload nothing")
    args = parser.parse_args(argv)
    try:
        api = os.environ.get("API_BASE_URL", "")
        article = fetch_article(args.slug, api) if api else None
        if args.cmd in ("validate", "render"):
            spec = _load(args.spec)
            errors = validate(spec, article)
            if errors:
                print("INVALID:\n- " + "\n- ".join(errors))
                return 1
            if args.cmd == "render":
                Path(args.out).write_text(render(spec, args.slug))
            print("OK" + ("" if article else " (number check skipped: API_BASE_URL not set)"))
            return 0
        cover, figure = _load(args.cover), _load(args.figure)
        errors = validate(cover, article) + validate(figure, article) + check_pair(cover, figure)
        if article is None and not args.dry_run:
            errors.append("API_BASE_URL is required to check the numbers against the article")
        if errors:
            print("INVALID:\n- " + "\n- ".join(errors))
            return 1
        svgs = {"cover": render(cover, args.slug), "figure": render(figure, args.slug)}
        if args.dry_run:
            out = Path(args.dry_run)
            out.mkdir(parents=True, exist_ok=True)
            for role, svg in svgs.items():
                (out / f"{role}.svg").write_text(svg)
            print(f"rendered to {out}")
            return 0
        urls = {
            role: upload(svg, args.slug, role, _env("SUPABASE_URL"), _env("SUPABASE_SECRET_KEY"))
            for role, svg in svgs.items()
        }
        attach(
            args.slug,
            {"src": urls["cover"], "alt": cover["alt"]},
            {"src": urls["figure"], "alt": figure["alt"], "caption": figure.get("caption", "")},
            _env("API_BASE_URL"),
            _env("EDITOR_API_KEY"),
        )
    except SpecError as exc:
        print(f"ERROR: {exc}")
        return 1
    print("attached cover and figure")
    return 0


if __name__ == "__main__":
    sys.exit(main())
