# Phase 2a: More Sources and a Scheduler Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ingest from four sources (Hacker News, RSS/Atom feeds, arXiv, Hugging Face daily papers) on a schedule, with per-source failure isolation.

**Architecture:** Each source is a `Source` plugin in `plugins/sources/`, registered by name in `plugins/sources/__init__.py`. A shared `fetch_bytes` helper in `_http.py` maps HTTP failures to the existing `SignalForgeError` types and retries via `call_with_retry`. One new worker command, `tick`, runs every source and then `assess`, so cron or launchd needs one entry. Dedupe already works by canonical URL; measuring duplicates and clustering is Phase 2b, a separate plan.

**Tech Stack:** Python 3.13, httpx, stdlib `xml.etree.ElementTree` (no new dependency), pydantic, pytest with `httpx.MockTransport`.

**Spec:** `docs/signalforge_prd.md` §Discovery (line 140) and the build-order row "2 Discovery" (line 887). Exit criterion for 2a: at least 4 sources ingesting continuously for 7 days.

## Global Constraints

- Python 3.13, ruff, mypy strict, pre-commit must pass. Conventional Commits, no AI or Co-Authored-By trailers.
- PRs at most 400 changed lines, squash-merged.
- No new runtime dependency. Parse XML with the stdlib.
- Sources emit `RawSignal` only and never touch the database. Failures raise `SignalForgeError` subtypes and never return partial results silently.
- Feed lists and queries are hard-coded defaults with a `ponytail:` comment until the vertical config exists.
- Never print `.env` values.

---

## File Structure

- Modify `src/signalforge/plugins/sources/_http.py`: add `fetch_bytes`.
- Create `src/signalforge/plugins/sources/feeds.py`: `parse_feed(xml: bytes) -> list[FeedEntry]` for RSS 2.0 and Atom.
- Create `src/signalforge/plugins/sources/rss.py`: `RssSource`.
- Create `src/signalforge/plugins/sources/arxiv.py`: `ArxivSource`.
- Create `src/signalforge/plugins/sources/huggingface.py`: `HuggingFacePapersSource`.
- Modify `src/signalforge/plugins/sources/__init__.py`: register the three sources.
- Create `apps/worker/tick.py`: run all sources, then assess.
- Tests: `tests/unit/test_feeds.py`, `test_rss_source.py`, `test_arxiv_source.py`, `test_hf_source.py`, `test_tick_cli.py`.
- Modify `README.md`, `.kiro/steering/tech.md`: commands and a cron line.

---

### Task 1: Shared fetch helper and feed parser

**Files:**
- Modify: `src/signalforge/plugins/sources/_http.py`
- Create: `src/signalforge/plugins/sources/feeds.py`
- Test: `tests/unit/test_feeds.py`

**Interfaces:**
- Produces:
  - `fetch_bytes(client: httpx.Client, url: str, *, label: str, params: dict[str, str | int] | None = None, sleep: Callable[[float], None] = time.sleep) -> bytes`. Retries via `call_with_retry`; maps timeout to `OperationTimeoutError`, transport errors and 5xx to `ProviderUnavailableError`, 429 to `RateLimitedError` (numeric `Retry-After` only), other 4xx to `ProviderRejectedError`.
  - `@dataclass(frozen=True) class FeedEntry: title: str; link: str; published: datetime | None; summary: str`.
  - `parse_feed(xml: bytes) -> list[FeedEntry]`. Raises `ArtifactValidationError` on malformed XML.

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_feeds.py
from datetime import UTC, datetime

import pytest

from signalforge.core.errors import ArtifactValidationError
from signalforge.plugins.sources.feeds import parse_feed

RSS = b"""<?xml version="1.0"?><rss version="2.0"><channel>
<item><title>Model X</title><link>https://a.example/x</link>
<pubDate>Sat, 26 Sep 2026 10:00:00 GMT</pubDate><description>Big &amp; new</description></item>
<item><title>No link</title></item>
</channel></rss>"""

ATOM = b"""<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom">
<entry><title>Paper Y</title><link rel="alternate" href="https://b.example/y"/>
<published>2026-09-26T10:00:00Z</published><summary>Abstract</summary></entry></feed>"""


def test_parses_rss() -> None:
    [entry] = parse_feed(RSS)
    assert entry.title == "Model X"
    assert entry.link == "https://a.example/x"
    assert entry.published == datetime(2026, 9, 26, 10, tzinfo=UTC)
    assert entry.summary == "Big & new"


def test_parses_atom() -> None:
    [entry] = parse_feed(ATOM)
    assert (entry.title, entry.link) == ("Paper Y", "https://b.example/y")
    assert entry.published == datetime(2026, 9, 26, 10, tzinfo=UTC)


def test_rejects_malformed_xml() -> None:
    with pytest.raises(ArtifactValidationError):
        parse_feed(b"<rss><oops")
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/unit/test_feeds.py -v`
Expected: FAIL (`ModuleNotFoundError: signalforge.plugins.sources.feeds`).

- [ ] **Step 3: Implement `feeds.py`**

```python
"""Parse RSS 2.0 and Atom into a flat list of entries. Entries without a link are dropped."""

import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime

from signalforge.core.errors import ArtifactValidationError

_ATOM = "{http://www.w3.org/2005/Atom}"


@dataclass(frozen=True)
class FeedEntry:
    title: str
    link: str
    published: datetime | None
    summary: str


def _text(node: ET.Element, *tags: str) -> str:
    for tag in tags:
        found = node.find(tag)
        if found is not None and found.text:
            return found.text.strip()
    return ""


def _date(value: str) -> datetime | None:
    if not value:
        return None
    try:
        parsed = (
            datetime.fromisoformat(value)
            if value[:4].isdigit()
            else parsedate_to_datetime(value)
        )
    except (ValueError, TypeError):
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _atom_link(entry: ET.Element) -> str:
    for link in entry.findall(f"{_ATOM}link"):
        if link.get("rel", "alternate") == "alternate" and link.get("href"):
            return link.get("href", "")
    return ""


def parse_feed(xml: bytes) -> list[FeedEntry]:
    try:
        root = ET.fromstring(xml)  # noqa: S314  (stdlib expat guards entity expansion)
    except ET.ParseError as exc:
        raise ArtifactValidationError("Feed is not valid XML") from exc
    entries: list[FeedEntry] = []
    for item in root.iter("item"):
        entries.append(
            FeedEntry(
                _text(item, "title"),
                _text(item, "link"),
                _date(_text(item, "pubDate")),
                _text(item, "description"),
            )
        )
    for entry in root.iter(f"{_ATOM}entry"):
        entries.append(
            FeedEntry(
                _text(entry, f"{_ATOM}title"),
                _atom_link(entry),
                _date(_text(entry, f"{_ATOM}published", f"{_ATOM}updated")),
                _text(entry, f"{_ATOM}summary", f"{_ATOM}content"),
            )
        )
    return [e for e in entries if e.link and e.title]
```

- [ ] **Step 4: Add `fetch_bytes` to `_http.py`**

Move the status-mapping logic from `hackernews.py::_get` into this function (same error types and messages, using `label` in place of "Hacker News"). Leave `hackernews.py` unchanged in this PR.

```python
def fetch_bytes(
    client: httpx.Client,
    url: str,
    *,
    label: str,
    params: dict[str, str | int] | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> bytes:
    def once() -> bytes:
        try:
            response = client.get(
                url, params=params, headers={"User-Agent": USER_AGENT}, timeout=REQUEST_TIMEOUT_S
            )
        except httpx.TimeoutException as exc:
            raise OperationTimeoutError(f"{label} request timed out") from exc
        except httpx.TransportError as exc:
            raise ProviderUnavailableError(f"{label} is unreachable") from exc
        status = response.status_code
        if status == httpx.codes.TOO_MANY_REQUESTS:
            retry_after = response.headers.get("Retry-After", "")
            raise RateLimitedError(
                f"{label} rate limited the request",
                retry_after_seconds=float(retry_after) if retry_after.isdigit() else None,
            )
        if status >= httpx.codes.INTERNAL_SERVER_ERROR:
            raise ProviderUnavailableError(f"{label} server error", context={"status": status})
        if status >= httpx.codes.BAD_REQUEST:
            raise ProviderRejectedError(f"{label} rejected the request", context={"status": status})
        return response.content

    return call_with_retry(once, sleep=sleep)
```

Add a test to `tests/unit/test_feeds.py` for the mapping (503 raises `ProviderUnavailableError` after retries with `sleep=lambda _: None`, 404 raises `ProviderRejectedError`, using `httpx.Client(transport=httpx.MockTransport(...))`).

- [ ] **Step 5: Run tests, lint, types**

Run: `uv run pytest tests/unit/test_feeds.py -v && uv run ruff check . && uv run mypy src`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/signalforge/plugins/sources/_http.py src/signalforge/plugins/sources/feeds.py tests/unit/test_feeds.py
git commit -m "feat: add feed parser and shared source fetch helper"
```

---

### Task 2: RSS/Atom source

**Files:**
- Create: `src/signalforge/plugins/sources/rss.py`
- Modify: `src/signalforge/plugins/sources/__init__.py`
- Test: `tests/unit/test_rss_source.py`

**Interfaces:**
- Consumes: `fetch_bytes`, `parse_feed`, `FeedEntry` from Task 1.
- Produces: `RssSource(client, *, feeds: Sequence[str] = DEFAULT_FEEDS, sleep=time.sleep)` with `name = "rss"`, `source_type = "blog"`, and `fetch(since) -> list[RawSignal]`. Registered as `"rss"`.

Default feeds (verify each URL returns 200 with `curl -sI` before committing; drop any that do not):
- `https://openai.com/news/rss.xml`
- `https://www.anthropic.com/news` has no feed, so skip it.
- `https://deepmind.google/blog/rss.xml`
- `https://huggingface.co/blog/feed.xml`
- `https://github.com/ollama/ollama/releases.atom`
- `https://github.com/vllm-project/vllm/releases.atom`
- `https://github.com/langchain-ai/langchain/releases.atom`

A feed that fails must not stop the others: log a warning with the feed URL and continue. If every feed fails, raise `ProviderUnavailableError`, because a source that returns nothing silently is the failure the Protocol forbids.

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_rss_source.py
from datetime import UTC, datetime

import httpx
import pytest

from signalforge.core.errors import ProviderUnavailableError
from signalforge.plugins.sources.rss import RssSource

FEED = b"""<?xml version="1.0"?><rss version="2.0"><channel>
<item><title>New</title><link>https://a.example/new?utm_source=x</link>
<pubDate>Sat, 26 Sep 2026 10:00:00 GMT</pubDate><description>Fresh</description></item>
<item><title>Old</title><link>https://a.example/old</link>
<pubDate>Mon, 01 Jan 2024 10:00:00 GMT</pubDate></item>
</channel></rss>"""
SINCE = datetime(2026, 9, 25, tzinfo=UTC)


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_returns_only_entries_since_and_canonicalises() -> None:
    src = RssSource(_client(lambda r: httpx.Response(200, content=FEED)), feeds=("https://f.example/rss",))
    [signal] = src.fetch(SINCE)
    assert signal.title == "New"
    assert signal.canonical_url == "https://a.example/new"
    assert signal.source == "rss"
    assert signal.metadata["feed"] == "https://f.example/rss"


def test_one_bad_feed_does_not_stop_others() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404) if "bad" in str(request.url) else httpx.Response(200, content=FEED)

    src = RssSource(_client(handler), feeds=("https://bad.example/rss", "https://ok.example/rss"))
    assert len(src.fetch(SINCE)) == 1


def test_all_feeds_failing_raises() -> None:
    src = RssSource(
        _client(lambda r: httpx.Response(404)), feeds=("https://bad.example/rss",), sleep=lambda _: None
    )
    with pytest.raises(ProviderUnavailableError):
        src.fetch(SINCE)
```

Note: the canonicaliser strips `utm_*` params already (see `core/canonical.py`); if it does not, adjust the test URL, not the canonicaliser.

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/unit/test_rss_source.py -v`
Expected: FAIL (module not found).

- [ ] **Step 3: Implement**

```python
"""Generic RSS/Atom source. Covers lab blogs and GitHub release feeds."""

import logging
import time
from collections.abc import Callable, Sequence
from datetime import datetime

import httpx
from pydantic import ValidationError

from signalforge.core.artifacts.signal import RawSignal
from signalforge.core.errors import ProviderUnavailableError, SignalForgeError
from signalforge.plugins.sources._http import fetch_bytes
from signalforge.plugins.sources.feeds import parse_feed

log = logging.getLogger(__name__)

# ponytail: hard-coded until the vertical config (ai_engineering.yaml) exists.
DEFAULT_FEEDS: tuple[str, ...] = (
    "https://openai.com/news/rss.xml",
    "https://deepmind.google/blog/rss.xml",
    "https://huggingface.co/blog/feed.xml",
    "https://github.com/ollama/ollama/releases.atom",
    "https://github.com/vllm-project/vllm/releases.atom",
    "https://github.com/langchain-ai/langchain/releases.atom",
)


class RssSource:
    name = "rss"
    source_type = "blog"

    def __init__(
        self,
        client: httpx.Client,
        *,
        feeds: Sequence[str] = DEFAULT_FEEDS,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._client = client
        self._feeds = tuple(feeds)
        self._sleep = sleep

    def fetch(self, since: datetime) -> list[RawSignal]:
        signals: dict[str, RawSignal] = {}
        failures = 0
        for feed in self._feeds:
            try:
                entries = parse_feed(
                    fetch_bytes(self._client, feed, label="Feed", sleep=self._sleep)
                )
            except SignalForgeError:
                failures += 1
                log.warning("feed failed", extra={"feed": feed}, exc_info=True)
                continue
            for entry in entries:
                if entry.published is None or entry.published <= since:
                    continue
                try:
                    signal = RawSignal(
                        source=self.name,
                        source_type=self.source_type,
                        canonical_url=entry.link,
                        title=entry.title,
                        summary=entry.summary,
                        published_at=entry.published,
                        metadata={"feed": feed},
                    )
                except ValidationError:
                    log.warning("skipping malformed entry", extra={"feed": feed})
                    continue
                signals.setdefault(signal.canonical_url, signal)
        if self._feeds and failures == len(self._feeds):
            raise ProviderUnavailableError("Every feed failed")
        return list(signals.values())
```

- [ ] **Step 4: Register in `__init__.py`**

Add `from signalforge.plugins.sources.rss import RssSource` and `RssSource.name: RssSource` to `_FACTORIES`. mypy: the factory type is `Callable[[httpx.Client], Source]`; the keyword-only args have defaults, so this type-checks.

- [ ] **Step 5: Run tests**

Run: `uv run pytest tests/unit -q && uv run ruff check . && uv run mypy src`
Expected: PASS.

- [ ] **Step 6: Live smoke check (no DB write)**

Run: `uv run python -c "import httpx; from signalforge.plugins.sources.rss import RssSource; from datetime import *; print(len(RssSource(httpx.Client(follow_redirects=True)).fetch(datetime.now(UTC)-timedelta(days=14))))"`
Expected: a positive count. Remove any default feed that fails, then re-run.

- [ ] **Step 7: Commit**

```bash
git add src/signalforge/plugins/sources/rss.py src/signalforge/plugins/sources/__init__.py tests/unit/test_rss_source.py
git commit -m "feat: add RSS/Atom source"
```

---

### Task 3: arXiv source

**Files:**
- Create: `src/signalforge/plugins/sources/arxiv.py`
- Modify: `src/signalforge/plugins/sources/__init__.py`
- Test: `tests/unit/test_arxiv_source.py`

**Interfaces:**
- Consumes: `fetch_bytes`, `parse_feed` (arXiv's API returns Atom).
- Produces: `ArxivSource(client, *, categories=("cs.AI", "cs.CL", "cs.LG"), max_results=100, sleep=time.sleep)` with `name = "arxiv"`, `source_type = "paper"`. Registered as `"arxiv"`.

Request: `GET https://export.arxiv.org/api/query` with `search_query="cat:cs.AI OR cat:cs.CL OR cat:cs.LG"`, `sortBy=submittedDate`, `sortOrder=descending`, `max_results=100`. arXiv asks for at most one request per three seconds; this source makes one request per run, so no throttle is needed. Keep entries with `published > since`. Titles contain newlines: collapse whitespace with `" ".join(title.split())`. Metadata: `{"categories": [...]}` is not available from `parse_feed`, so skip it.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_arxiv_source.py
from datetime import UTC, datetime

import httpx

from signalforge.plugins.sources.arxiv import ArxivSource

ATOM = b"""<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom">
<entry><title>Scaling
  Agents</title><link rel="alternate" href="http://arxiv.org/abs/2609.00001v1"/>
<published>2026-09-26T10:00:00Z</published><summary>We study agents.</summary></entry>
<entry><title>Old paper</title><link rel="alternate" href="http://arxiv.org/abs/2401.00001v1"/>
<published>2024-01-01T10:00:00Z</published><summary>Old.</summary></entry></feed>"""


def test_fetch_filters_by_date_and_cleans_title() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, content=ATOM)

    src = ArxivSource(httpx.Client(transport=httpx.MockTransport(handler)))
    [signal] = src.fetch(datetime(2026, 9, 25, tzinfo=UTC))
    assert signal.title == "Scaling Agents"
    assert signal.source_type == "paper"
    assert "cat:cs.AI" in seen[0].url.params["search_query"]
```

- [ ] **Step 2: Run to verify failure**, then **Step 3: implement** `ArxivSource` following the `RssSource` shape (single request, `fetch_bytes(..., label="arXiv", params=...)`, `parse_feed`, filter, build `RawSignal`, dedupe by canonical URL). Strip the `vN` version suffix from the link with `re.sub(r"v\d+$", "", link)` so a paper revision does not create a second signal.

- [ ] **Step 4: Register `"arxiv"`, run tests, lint, types.**

Run: `uv run pytest tests/unit -q && uv run ruff check . && uv run mypy src`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/signalforge/plugins/sources/arxiv.py src/signalforge/plugins/sources/__init__.py tests/unit/test_arxiv_source.py
git commit -m "feat: add arXiv source"
```

---

### Task 4: Hugging Face daily papers source

**Files:**
- Create: `src/signalforge/plugins/sources/huggingface.py`
- Modify: `src/signalforge/plugins/sources/__init__.py`
- Test: `tests/unit/test_hf_source.py`

**Interfaces:**
- Consumes: `fetch_bytes`.
- Produces: `HuggingFacePapersSource(client, *, sleep=time.sleep)` with `name = "huggingface"`, `source_type = "paper"`. Registered as `"huggingface"`.

Endpoint: `GET https://huggingface.co/api/daily_papers`. Before writing the model, run `curl -s https://huggingface.co/api/daily_papers | head -c 1500` and confirm the field names. Expected shape per item: `{"paper": {"id": "2609.00001", "title": ..., "summary": ..., "upvotes": 12}, "publishedAt": "2026-09-26T10:00:00.000Z"}`. Model it with pydantic `extra="ignore"` (same style as `hackernews.py::_Hit`). Signal URL: `https://huggingface.co/papers/{id}`. Metadata: `{"upvotes": n, "arxiv_id": id}`. Malformed shape raises `ArtifactValidationError`.

- [ ] **Step 1: Write the failing test** with a fixture JSON of two items (one before `since`), asserting one signal, URL `https://huggingface.co/papers/2609.00001`, and `metadata["upvotes"]`. Add a second test that a body of `{"oops": 1}` raises `ArtifactValidationError`.
- [ ] **Step 2: Run to verify failure.**
- [ ] **Step 3: Implement** with two small pydantic models (`_Paper`, `_Item`) and `TypeAdapter(list[_Item]).validate_json(body)`.
- [ ] **Step 4: Register, run tests, lint, types.**
- [ ] **Step 5: Commit**

```bash
git add src/signalforge/plugins/sources/huggingface.py src/signalforge/plugins/sources/__init__.py tests/unit/test_hf_source.py
git commit -m "feat: add Hugging Face papers source"
```

---

### Task 5: `tick` command and docs

**Files:**
- Create: `apps/worker/tick.py`
- Modify: `README.md`, `.kiro/steering/tech.md`
- Test: `tests/unit/test_tick_cli.py`

**Interfaces:**
- Consumes: `SOURCE_NAMES`, `build_source`, `run_ingest`, and the `run_assess` entry used by `apps/worker/assess.py` (read that file first to reuse its setup; if assess setup lives inside `main`, extract a `run(limit)` function in `assess.py` and call it, keeping the CLI behaviour identical).
- Produces: `uv run python -m apps.worker.tick [--hours N] [--assess-limit N]`. Ingests every source in `SOURCE_NAMES`, one failure logged and counted but never stopping the rest, then runs assess. Exit code 0 when at least one source succeeded, 1 when all failed.

- [ ] **Step 1: Write the failing test.** Patch `build_source` and `run_ingest` (as `tests/unit/test_ingest_cli.py` does; follow its pattern) so one source raises; assert the others still run, assess is called once, and the exit code is 0. A second test: all sources raise, exit code 1.
- [ ] **Step 2: Run to verify failure.**
- [ ] **Step 3: Implement `tick.py`.** Loop over `SOURCE_NAMES`, wrap each `run_ingest` in `try/except SignalForgeError`, log with `log.exception`, count successes. Call assess only when the LLM provider is configured (`settings.llm_provider != "fake"`), otherwise log that assess was skipped. Return the exit code.
- [ ] **Step 4: Docs.** Add to README and `tech.md`: the command, and this cron line for every 30 minutes:

```
*/30 * * * * cd /Users/suraj/personal/signalforge && uv run python -m apps.worker.tick >> /tmp/signalforge-tick.log 2>&1
```

Note that assess needs `LLM_PROVIDER`, `LLM_BASE_URL` and `LLM_MODEL_RELEVANCE` in `.env`.
- [ ] **Step 5: Run the full check**

Run: `uv run pytest -q && uv run ruff check . && uv run mypy src`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add apps/worker/tick.py apps/worker/assess.py README.md .kiro/steering/tech.md tests/unit/test_tick_cli.py
git commit -m "feat: add tick command to run all sources and assess"
```

---

## Acceptance (after merge, on the dev DB)

- [ ] `uv run python -m apps.worker.tick --hours 72` exits 0 and `select source, count(*) from signals group by 1` shows four sources.
- [ ] Install the cron line; after 7 days, `stage_runs` shows successful `ingest` rows for all four sources on most days. Record the result in the Phase 2 exit note.

## Self-Review

- **Spec coverage:** PRD Phase 2 lists GitHub, HN, RSS, arXiv/HF. HN exists (1.5); RSS covers lab blogs and GitHub release feeds (Task 2); arXiv (3) and HF (4) added. GitHub trending is not covered: it has no official API, so 2a uses release feeds only. Normalization and canonicalization already exist (`RawSignal`). Dedupe by canonical URL exists; **duplicate-rate measurement and clustering are deferred to Phase 2b** (own plan, needs embeddings and a labeled sample).
- **Placeholders:** Tasks 3 and 4 give the shape and the test's asserted values but leave the mechanical `RawSignal` construction to follow Task 2. HF field names are confirmed live in Task 4 before coding.
- **Type consistency:** `fetch_bytes`, `parse_feed`, `FeedEntry` and the `sleep` keyword are used with the same names in Tasks 2 to 4.
- **Known ceilings:** arXiv volume (100 per run) means many signals reach assess. Cost is about $0.0001 per signal at current prices, so this is fine for now. Revisit if volume grows.
