# Deep Research Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn an accepted `topic_cards` row into a `ResearchPackage`: fetched primary + secondary sources, extracted claims each mapped to a verbatim evidence span.

**Architecture:** A new `stages/research.py` plain function (`run_research`, mirrors `run_assess`) reads accepted cards with no existing `research_packages` row, fetches the primary source (httpx + trafilatura), searches Tavily for secondary sources, calls a new `research_extraction` LLM role once per document, mechanically verifies each claim's quoted span exists in the source text, merges claims across documents, and writes one `research_packages` row per card.

**Tech Stack:** Existing stack (SQLAlchemy, Alembic, Pydantic, httpx, pytest). New: `trafilatura` (HTML extraction), Tavily HTTP API (no SDK, plain httpx like other plugins).

**Spec:** `docs/superpowers/specs/2026-09-27-research-pipeline-design.md`

## Global Constraints

- Claim status is always `"unverified"` when written by this stage. FR-08 (a separate, later sub-project) assigns real status. Do not implement status assignment here.
- Budget scope is `BudgetScope.TOPIC`, limit `Settings.budget_per_topic_usd` (already exists, default `Decimal("0.50")`). Reuse `core/budget.py` as-is; no new budget type.
- Secondary source cap is exactly 3 per card (fixed, not configurable via settings for V1).
- No live network calls (Tavily or HTTP fetch) in any test. Fake the client, following `plugins/sources` test patterns.
- `ResearchPackage` extends `core/artifacts/base.Artifact`. Frozen, `extra="forbid"`, gets `id`/`schema_version`/`created_at`/`produced_by`/`parent_ids` for free.
- New table `research_packages`: UUID PK, `TimestampsMixin`, `SchemaVersionMixin` (same base as `topic_cards`), one row per `card_id` (unique constraint).
- No new `research_status` column on `topic_cards`. Status lives only on `research_packages.status`.
- Never print `.env` values or the `TAVILY_API_KEY` value in code, logs, or commits.

---

### Task 1: `research_packages` table and row model

**Files:**
- Create: `src/signalforge/db/migrations/versions/0006_add_research_packages.py`
- Create: `src/signalforge/db/models/research.py`
- Modify: `src/signalforge/db/models/__init__.py` (export `ResearchPackageRow`)
- Test: `tests/db/test_research_model.py`

**Interfaces:**
- Produces: `ResearchPackageRow` (SQLAlchemy model), columns below. Later tasks read/write this row directly (no repository class needed for V1 — one query pattern, matches `AssessmentRepository`'s simplicity, but this task does NOT add a repository; Task 5 queries the model directly, following `run_assess`'s direct-session-query style).

Columns (mirrors `TopicCardRow`'s style in `db/models/cards.py`):

```python
"""Research packages: fetched sources and extracted claims for an accepted topic card."""

import uuid

from sqlalchemy import CheckConstraint, ForeignKey, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from signalforge.db.base import Base, SchemaVersionMixin, TimestampsMixin, UUIDPrimaryKeyMixin


class ResearchPackageRow(Base, UUIDPrimaryKeyMixin, TimestampsMixin, SchemaVersionMixin):
    __tablename__ = "research_packages"
    __table_args__ = (
        UniqueConstraint("card_id", name="uq_research_packages_card_id"),
        CheckConstraint(
            "status IN ('researching', 'researched', 'needs_more_info', 'failed')",
            name="ck_research_packages_status_allowed",
        ),
    )

    card_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("topic_cards.id", ondelete="CASCADE")
    )
    status: Mapped[str] = mapped_column(default="researching")
    documents: Mapped[list[dict]] = mapped_column(JSONB, default=list)
    claims: Mapped[list[dict]] = mapped_column(JSONB, default=list)
    gaps_and_disagreements: Mapped[str] = mapped_column(Text, default="")
    cost_usd: Mapped[str] = mapped_column(Text, default="0")
    calls: Mapped[int] = mapped_column(default=0)
    tokens: Mapped[int] = mapped_column(default=0)
```

`cost_usd` is `Text` storing a `Decimal`'s `str()`, matching how the rest of the codebase avoids float drift without introducing a `Numeric` column type this task doesn't otherwise need — check `db/models/ops.py`'s `LLMCall.cost_usd` column type first and copy that type exactly instead if it differs (it likely uses `Numeric(12, 6)`; use the same type for consistency).

- [ ] **Step 1: Check the exact column type `LLMCall.cost_usd` uses**

Run: `grep -n "cost_usd" src/signalforge/db/models/ops.py`

Use that same SQLAlchemy type (likely `Numeric(12, 6)`) for `ResearchPackageRow.cost_usd` instead of `Text`, and match it in the migration below.

- [ ] **Step 2: Write the model file**

Create `src/signalforge/db/models/research.py` with the class above, corrected for the real `cost_usd` type from Step 1.

- [ ] **Step 3: Export it**

Add `from signalforge.db.models.research import ResearchPackageRow` and add `"ResearchPackageRow"` to `__all__` in `src/signalforge/db/models/__init__.py` (match the existing entries' style exactly).

- [ ] **Step 4: Write the migration**

Create `src/signalforge/db/migrations/versions/0006_add_research_packages.py`, following `0005_add_topic_cards.py`'s exact structure (`_common_columns()` helper import pattern, `upgrade()`/`downgrade()`):

```python
"""add research packages

Revision ID: 0006
Revises: 0005
Create Date: 2026-09-27
"""

from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _common_columns() -> list[sa.Column[Any]]:
    return [
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    ]


def upgrade() -> None:
    op.create_table(
        "research_packages",
        sa.Column("card_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=32), server_default="researching", nullable=False),
        sa.Column("documents", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("claims", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("gaps_and_disagreements", sa.Text(), server_default="", nullable=False),
        sa.Column("cost_usd", sa.Numeric(12, 6), server_default=sa.text("0"), nullable=False),
        sa.Column("calls", sa.Integer(), server_default="0", nullable=False),
        sa.Column("tokens", sa.Integer(), server_default="0", nullable=False),
        *_common_columns(),
        sa.CheckConstraint(
            "status IN ('researching', 'researched', 'needs_more_info', 'failed')",
            name=op.f("ck_research_packages_status_allowed"),
        ),
        sa.ForeignKeyConstraint(
            ["card_id"], ["topic_cards.id"], name="fk_research_packages_card_id_topic_cards",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_research_packages"),
        sa.UniqueConstraint("card_id", name="uq_research_packages_card_id"),
    )


def downgrade() -> None:
    op.drop_table("research_packages")
```

Adjust `cost_usd`'s SQLAlchemy type/migration type together if Step 1 found something other than `Numeric(12, 6)`.

- [ ] **Step 5: Write the failing test**

```python
"""tests/db/test_research_model.py"""
import uuid

from signalforge.db.models import ResearchPackageRow


def test_research_package_row_defaults():
    row = ResearchPackageRow(card_id=uuid.uuid4())
    assert row.status == "researching"
    assert row.documents == []
    assert row.claims == []
```

- [ ] **Step 6: Run migration against the dev DB and run the test**

Run: `uv run alembic upgrade head && uv run pytest tests/db/test_research_model.py -v`
Expected: PASS. If no dev DB is reachable in this sandbox, run `uv run alembic upgrade head --sql` to at least validate the migration generates without error, note this in the report.

- [ ] **Step 7: Commit**

```bash
git add src/signalforge/db/models/research.py src/signalforge/db/models/__init__.py src/signalforge/db/migrations/versions/0006_add_research_packages.py tests/db/test_research_model.py
git commit -m "feat: add research_packages table and row model"
```

---

### Task 2: `ResearchPackage` artifact and extraction data types

**Files:**
- Create: `src/signalforge/core/artifacts/research.py`
- Test: `tests/core/artifacts/test_research.py`

**Interfaces:**
- Consumes: `Artifact` base (`core/artifacts/base.py`).
- Produces: `ResearchDocument`, `ResearchClaim` (plain Pydantic models, not artifacts themselves — they are nested inside `ResearchPackage`), `ResearchPackage(Artifact)`. Task 4 and 5 import and construct these.

```python
"""ResearchPackage: fetched sources and extracted claims for one accepted topic card (FR-06)."""

from typing import ClassVar
from uuid import UUID

from pydantic import BaseModel, Field

from signalforge.core.artifacts.base import Artifact


class ResearchDocument(BaseModel):
    model_config = {"frozen": True, "extra": "forbid"}

    url: str
    title: str
    source_label: str
    is_primary: bool
    raw_text_ref: str


class ResearchClaim(BaseModel):
    model_config = {"frozen": True, "extra": "forbid"}

    text: str = Field(min_length=1)
    evidence_span: str = Field(min_length=1)
    document_indices: tuple[int, ...]
    status: str = "unverified"


class ResearchPackage(Artifact):
    SCHEMA_VERSION: ClassVar[int] = 1

    card_id: UUID
    status: str = "researching"
    documents: tuple[ResearchDocument, ...] = ()
    claims: tuple[ResearchClaim, ...] = ()
    gaps_and_disagreements: str = ""
```

- [ ] **Step 1: Write the failing test**

```python
"""tests/core/artifacts/test_research.py"""
from uuid import uuid4

from signalforge.core.artifacts.research import ResearchClaim, ResearchDocument, ResearchPackage


def test_research_package_is_frozen_and_forbids_unknown_fields():
    pkg = ResearchPackage(card_id=uuid4())
    assert pkg.status == "researching"
    try:
        pkg.status = "researched"  # type: ignore[misc]
        raised = False
    except Exception:
        raised = True
    assert raised


def test_research_claim_holds_document_indices():
    claim = ResearchClaim(text="X does Y", evidence_span="X does Y", document_indices=(0, 2))
    assert claim.status == "unverified"
    assert claim.document_indices == (0, 2)


def test_research_document_requires_all_fields():
    doc = ResearchDocument(
        url="https://example.com", title="T", source_label="Example",
        is_primary=True, raw_text_ref="blob://abc",
    )
    assert doc.is_primary is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/core/artifacts/test_research.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Write the implementation**

Create `src/signalforge/core/artifacts/research.py` with the code above.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/core/artifacts/test_research.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/signalforge/core/artifacts/research.py tests/core/artifacts/test_research.py
git commit -m "feat: add ResearchPackage artifact"
```

---

### Task 3: HTML extraction and mechanical span check

**Files:**
- Create: `src/signalforge/stages/research_extraction.py`
- Test: `tests/stages/test_research_extraction.py`
- Modify: `pyproject.toml` (add `trafilatura` dependency)

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `extract_clean_text(html: str) -> str | None` (returns `None` if extraction yields nothing usable), `span_exists(span: str, document_text: str) -> bool`, `merge_claims(candidates: list[tuple[int, ResearchClaim]]) -> tuple[ResearchClaim, ...]` where the `int` is the document index the claim came from and identical `text` values (case-sensitive, exact match after `.strip()`) get merged into one `ResearchClaim` with combined `document_indices`. Task 5 calls all three.

- [ ] **Step 1: Add the dependency**

Run: `uv add "trafilatura>=1.12,<2"`

- [ ] **Step 2: Write the failing tests**

```python
"""tests/stages/test_research_extraction.py"""
from signalforge.core.artifacts.research import ResearchClaim
from signalforge.stages.research_extraction import extract_clean_text, merge_claims, span_exists

_HTML = """
<html><body>
<nav>Home | About | Contact</nav>
<article><h1>Model X released</h1><p>Model X reaches 90% accuracy on benchmark Y.</p></article>
<footer>Copyright 2026</footer>
</body></html>
"""


def test_extract_clean_text_drops_nav_and_footer():
    text = extract_clean_text(_HTML)
    assert text is not None
    assert "90% accuracy" in text
    assert "Home | About | Contact" not in text
    assert "Copyright 2026" not in text


def test_extract_clean_text_returns_none_for_empty_input():
    assert extract_clean_text("<html><body></body></html>") is None


def test_span_exists_exact_match():
    assert span_exists("Model X reaches 90% accuracy", "Model X reaches 90% accuracy on Y.")


def test_span_exists_false_for_paraphrase():
    assert not span_exists("Model X hits ninety percent", "Model X reaches 90% accuracy on Y.")


def test_merge_claims_combines_identical_text():
    a = ResearchClaim(text="X does Y", evidence_span="X does Y", document_indices=(0,))
    b = ResearchClaim(text="X does Y", evidence_span="X does Y exactly", document_indices=(1,))
    merged = merge_claims([(0, a), (1, b)])
    assert len(merged) == 1
    assert set(merged[0].document_indices) == {0, 1}


def test_merge_claims_keeps_distinct_claims_separate():
    a = ResearchClaim(text="X does Y", evidence_span="X does Y", document_indices=(0,))
    b = ResearchClaim(text="X does Z", evidence_span="X does Z", document_indices=(0,))
    merged = merge_claims([(0, a), (0, b)])
    assert len(merged) == 2
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/stages/test_research_extraction.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 4: Write the implementation**

```python
"""Clean-text extraction and the mechanical evidence checks for research (FR-06).

The mechanical span check catches a hallucinated quote before it ever reaches
FR-08's LLM judge: cheap, exact, and it never needs a model call.
"""

from collections import defaultdict

import trafilatura

from signalforge.core.artifacts.research import ResearchClaim


def extract_clean_text(html: str) -> str | None:
    text = trafilatura.extract(html)
    return text if text else None


def span_exists(span: str, document_text: str) -> bool:
    return span.strip() in document_text


def merge_claims(candidates: list[tuple[int, ResearchClaim]]) -> tuple[ResearchClaim, ...]:
    by_text: dict[str, list[tuple[int, ResearchClaim]]] = defaultdict(list)
    for doc_index, claim in candidates:
        by_text[claim.text.strip()].append((doc_index, claim))

    merged: list[ResearchClaim] = []
    for group in by_text.values():
        indices = tuple(sorted({doc_index for doc_index, _ in group}))
        first_claim = group[0][1]
        merged.append(first_claim.model_copy(update={"document_indices": indices}))
    return tuple(merged)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/stages/test_research_extraction.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml uv.lock src/signalforge/stages/research_extraction.py tests/stages/test_research_extraction.py
git commit -m "feat: add HTML extraction and mechanical span check"
```

---

### Task 4: Tavily client and `research_extraction` LLM role

**Files:**
- Create: `src/signalforge/plugins/search/tavily.py`
- Modify: `src/signalforge/llm/roles.py` (add `research_extraction` role)
- Modify: `src/signalforge/core/config.py` (add `tavily_api_key: SecretStr | None`, `llm_model_research_extraction: str = "openai/gpt-4o-mini"`)
- Modify: `apps/web/.env.local.example` if it exists, else create `.env.example` at repo root if one exists — check first: run `ls .env.example .env.local.example 2>/dev/null` and add `TAVILY_API_KEY=` to whichever file(s) exist, following the existing format
- Test: `tests/plugins/search/test_tavily.py`

**Interfaces:**
- Consumes: `httpx.Client` (constructor arg, same pattern as `HackerNewsSource`), `Settings.tavily_api_key`.
- Produces: `TavilySearchResult(url: str, title: str)` (Pydantic), `TavilyClient(client: httpx.Client, api_key: str).search(query: str, max_results: int = 3) -> list[TavilySearchResult]`. Task 5 calls `.search(...)`. Also produces the `"research_extraction"` key added to `RoleMap` — Task 5 passes this string to `gateway.model_for("research_extraction")` / `gateway.complete_json(role="research_extraction", ...)`.

- [ ] **Step 1: Check which env-example file(s) exist**

Run: `ls .env.example .env.local.example apps/web/.env.local.example 2>/dev/null`

Add `TAVILY_API_KEY=` (no value) to whichever repo-root file exists, matching its existing line format. Do not touch `apps/web/.env.local.example` — that file is for the Next.js app, unrelated to this Python-side key.

- [ ] **Step 2: Add settings fields**

In `src/signalforge/core/config.py`, alongside the existing `llm_model_relevance`/`llm_model_topic_card` fields, add:

```python
    llm_model_research_extraction: str = "openai/gpt-4o-mini"
```

Alongside `llm_api_key`, add:

```python
    tavily_api_key: SecretStr | None = Field(default=None, validation_alias="TAVILY_API_KEY")
```

- [ ] **Step 3: Add the LLM role**

In `src/signalforge/llm/roles.py`'s `build_roles()`, add:

```python
        "research_extraction": _spec(settings.llm_model_research_extraction),
```

- [ ] **Step 4: Write the failing test for the Tavily client**

```python
"""tests/plugins/search/test_tavily.py"""
import httpx
import pytest

from signalforge.plugins.search.tavily import TavilyClient


def _fake_transport(request: httpx.Request) -> httpx.Response:
    assert request.url.path == "/search"
    return httpx.Response(
        200,
        json={
            "results": [
                {"url": "https://a.example.com", "title": "A"},
                {"url": "https://b.example.com", "title": "B"},
                {"url": "https://c.example.com", "title": "C"},
                {"url": "https://d.example.com", "title": "D"},
            ]
        },
    )


def test_search_caps_at_max_results():
    client = httpx.Client(transport=httpx.MockTransport(_fake_transport))
    tavily = TavilyClient(client, api_key="fake-key")
    results = tavily.search("model X release", max_results=3)
    assert len(results) == 3
    assert results[0].url == "https://a.example.com"


def test_search_raises_provider_unavailable_on_5xx():
    from signalforge.core.errors import ProviderUnavailableError

    def _fail(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    client = httpx.Client(transport=httpx.MockTransport(_fail))
    tavily = TavilyClient(client, api_key="fake-key")
    with pytest.raises(ProviderUnavailableError):
        tavily.search("q")
```

- [ ] **Step 5: Run test to verify it fails**

Run: `uv run pytest tests/plugins/search/test_tavily.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 6: Write the implementation**

```python
"""Tavily search: secondary-source discovery for the research stage (FR-06).

The only module that knows Tavily's request/response shape; the research
stage sees plain search results.
"""

import httpx
from pydantic import BaseModel, ConfigDict

from signalforge.core.errors import ProviderUnavailableError

SEARCH_URL = "https://api.tavily.com/search"
REQUEST_TIMEOUT_S = 10.0


class TavilySearchResult(BaseModel):
    model_config = ConfigDict(extra="ignore")

    url: str
    title: str


class TavilyClient:
    def __init__(self, client: httpx.Client, *, api_key: str) -> None:
        self._client = client
        self._api_key = api_key

    def search(self, query: str, *, max_results: int = 3) -> list[TavilySearchResult]:
        response = self._client.post(
            SEARCH_URL,
            json={"api_key": self._api_key, "query": query, "max_results": max_results},
            timeout=REQUEST_TIMEOUT_S,
        )
        if response.status_code >= 500:
            raise ProviderUnavailableError(
                "Tavily unavailable", context={"status": response.status_code}
            )
        response.raise_for_status()
        results = [TavilySearchResult.model_validate(r) for r in response.json()["results"]]
        return results[:max_results]
```

- [ ] **Step 7: Run test to verify it passes**

Run: `uv run pytest tests/plugins/search/test_tavily.py -v`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add src/signalforge/plugins/search/tavily.py src/signalforge/llm/roles.py src/signalforge/core/config.py tests/plugins/search/test_tavily.py
# also add whichever .env.example file was edited in Step 1
git commit -m "feat: add Tavily search client and research_extraction role"
```

---

### Task 5: Research stage orchestration

**Files:**
- Create: `src/signalforge/stages/research.py`
- Test: `tests/stages/test_research.py`

**Interfaces:**
- Consumes: `ResearchPackage`/`ResearchDocument`/`ResearchClaim` (Task 2), `extract_clean_text`/`span_exists`/`merge_claims` (Task 3), `TavilyClient`/`TavilySearchResult` (Task 4), `LLMGateway.complete_json(role=..., system=..., user=..., schema=..., stage_run_id=...)` (existing, `llm/gateway.py`), `Budget`/`BudgetScope.TOPIC`/`BudgetExceededError` (existing, `core/budget.py`), `ResearchPackageRow` (Task 1), `TopicCardRow`/`EditorDecisionRow` (existing, `db/models/cards.py`).
- Produces: `RESEARCH_STAGE = "research"`, `ROLE = "research_extraction"`, `PROMPT_VERSION = "research-v1"`, `@dataclass(frozen=True) ResearchResult(considered: int, researched: int, needs_more_info: int, failed: int, stage_run_id: uuid.UUID)`, `run_research(session, gateway_factory, http_client, tavily, *, limit: int = 10) -> ResearchResult` where `gateway_factory: Callable[[Session, Budget], LLMGateway]` (note: this differs from `run_assess`'s `gateway_factory` — that one takes only `Session` because assess uses one shared budget for the whole batch; research needs one fresh `Budget` per card, so `gateway_factory` here takes the per-card `Budget` too, and is called once per card, not once per run). `LLMGateway.__init__` already takes a `budget` argument (confirmed in `llm/gateway.py`), so this factory shape is just "construct a gateway with this card's budget." Nothing later in this plan consumes this, but a future CLI wiring task (out of scope here, same as `run_assess` was wired into `tick` in a separate earlier plan) will call `run_research` the same way.

- [ ] **Step 1: Write the failing tests**

```python
"""tests/stages/test_research.py"""
import uuid
from datetime import UTC, datetime
from unittest.mock import MagicMock

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from signalforge.core.artifacts.research import ResearchClaim
from signalforge.core.budget import Budget, BudgetExceededError, BudgetLimits, BudgetScope
from signalforge.db.models import EditorDecisionRow, ResearchPackageRow, Signal, TopicCardRow
from signalforge.plugins.search.tavily import TavilySearchResult
from signalforge.stages.research import run_research


def _make_accepted_card(session: Session) -> TopicCardRow:
    signal = Signal(
        source="hackernews", source_type="community", canonical_url="https://x.example.com",
        title="Model X released", published_at=datetime.now(UTC), content_hash="h1",
    )
    session.add(signal)
    session.flush()
    card = TopicCardRow(
        signal_id=signal.id, stage_run_id=uuid.uuid4(), what_happened="Model X released",
        why_it_matters="Big deal", novelty=0.8, signal_strength=0.8, coverage_gap="none",
        suggested_angle="explainer", format="explainer", evergreen_score=0.5, confidence=0.8,
        risk_flags=[], prompt_version="cards-v1", model="openai/gpt-4o-mini",
    )
    session.add(card)
    session.flush()
    session.add(EditorDecisionRow(topic_card_id=card.id, decision="accepted"))
    session.commit()
    return card


def _fake_gateway_factory(claims_json: str):
    def factory(session, budget):
        gateway = MagicMock()
        gateway.model_for.return_value = "openai/gpt-4o-mini"
        gateway.complete_json.return_value = _ClaimsReply.model_validate_json(claims_json)
        return gateway
    return factory


from pydantic import BaseModel


class _ClaimsReply(BaseModel):
    claims: list[dict]


def test_run_research_produces_researched_package(db_session):
    card = _make_accepted_card(db_session)

    def primary_fetch(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, html="<html><body><article><p>Model X reaches 90% accuracy.</p></article></body></html>")

    http_client = httpx.Client(transport=httpx.MockTransport(primary_fetch))
    tavily = MagicMock()
    tavily.search.return_value = []
    claims_json = '{"claims": [{"text": "Model X reaches 90% accuracy", "evidence_span": "Model X reaches 90% accuracy"}]}'
    gateway_factory = _fake_gateway_factory(claims_json)

    result = run_research(db_session, gateway_factory, http_client, tavily)

    assert result.researched == 1
    row = db_session.scalars(select(ResearchPackageRow).where(ResearchPackageRow.card_id == card.id)).one()
    assert row.status == "researched"
    assert len(row.claims) == 1


def test_run_research_needs_more_info_when_primary_fetch_fails(db_session):
    _make_accepted_card(db_session)

    def failing_fetch(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404)

    http_client = httpx.Client(transport=httpx.MockTransport(failing_fetch))
    tavily = MagicMock()
    tavily.search.return_value = []
    result = run_research(db_session, _fake_gateway_factory('{"claims": []}'), http_client, tavily)

    assert result.needs_more_info == 1
    row = db_session.scalars(select(ResearchPackageRow)).one()
    assert row.status == "needs_more_info"


def test_run_research_needs_more_info_when_no_claims_survive(db_session):
    _make_accepted_card(db_session)

    def primary_fetch(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, html="<html><body><article><p>Some text.</p></article></body></html>")

    http_client = httpx.Client(transport=httpx.MockTransport(primary_fetch))
    tavily = MagicMock()
    tavily.search.return_value = []
    # LLM returns a claim whose span does NOT exist verbatim in the source text.
    claims_json = '{"claims": [{"text": "fabricated", "evidence_span": "this span is not in the source"}]}'
    result = run_research(db_session, _fake_gateway_factory(claims_json), http_client, tavily)

    assert result.needs_more_info == 1


def test_run_research_skips_cards_with_existing_package(db_session):
    card = _make_accepted_card(db_session)
    db_session.add(ResearchPackageRow(card_id=card.id, status="researched"))
    db_session.commit()

    result = run_research(db_session, _fake_gateway_factory('{"claims": []}'), MagicMock(), MagicMock())
    assert result.considered == 0
```

Note: `db_session` fixture — check `tests/conftest.py` for the existing session/DB fixture name and adapt these tests to use whatever fixture `test_assess.py` or `test_research_model.py` (Task 1) already relies on; do not invent a new fixture.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/stages/test_research.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Write the implementation**

```python
"""Research: turn an accepted topic card into a ResearchPackage (FR-06).

Plain function like ``run_assess``; records itself in ``stage_runs``.
"""

import logging
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

import httpx
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from signalforge.core.artifacts.research import ResearchClaim, ResearchDocument
from signalforge.core.budget import Budget, BudgetExceededError, BudgetLimits, BudgetScope
from signalforge.core.errors import PermanentError, RetryableError
from signalforge.core.logging import correlation_id
from signalforge.db.models import EditorDecisionRow, ResearchPackageRow, StageRun, StageRunStatus, TopicCardRow
from signalforge.llm.gateway import LLMGateway
from signalforge.plugins.search.tavily import TavilyClient
from signalforge.stages.ingest import _ENTITY_NAMESPACE, _sha
from signalforge.stages.research_extraction import extract_clean_text, merge_claims, span_exists

log = logging.getLogger(__name__)

RESEARCH_STAGE = "research"
ROLE = "research_extraction"
PROMPT_VERSION = "research-v1"
SECONDARY_SOURCE_CAP = 3
REQUEST_TIMEOUT_S = 10.0

_SYSTEM = """You extract factual claims from a source document about a topic in AI \
engineering. Each claim must include a verbatim quoted span copied exactly from the \
document; never paraphrase the span. Reply with JSON only: \
{"claims": [{"text": "...", "evidence_span": "..."}]}"""


class _CandidateClaim(BaseModel):
    text: str
    evidence_span: str


class _ClaimsReply(BaseModel):
    claims: list[_CandidateClaim]


@dataclass(frozen=True)
class ResearchResult:
    considered: int
    researched: int
    needs_more_info: int
    failed: int
    stage_run_id: uuid.UUID


def _fetch_text(http_client: httpx.Client, url: str) -> str | None:
    try:
        response = http_client.get(url, timeout=REQUEST_TIMEOUT_S)
    except httpx.HTTPError:
        return None
    if response.status_code >= 400:
        return None
    return extract_clean_text(response.text)


def _extract_claims_for_document(
    gateway: LLMGateway, stage_run_id: uuid.UUID, document_text: str
) -> list[_CandidateClaim]:
    reply = gateway.complete_json(
        role=ROLE,
        system=_SYSTEM,
        user=document_text[:8000],
        schema=_ClaimsReply,
        stage_run_id=stage_run_id,
    )
    return reply.claims


def _accepted_cards_without_package(session: Session, limit: int) -> list[TopicCardRow]:
    accepted_ids = select(EditorDecisionRow.topic_card_id).where(
        EditorDecisionRow.decision == "accepted"
    )
    existing_ids = select(ResearchPackageRow.card_id)
    stmt = (
        select(TopicCardRow)
        .where(TopicCardRow.id.in_(accepted_ids))
        .where(TopicCardRow.id.not_in(existing_ids))
        .limit(limit)
    )
    return list(session.scalars(stmt))


def run_research(
    session: Session,
    gateway_factory: Callable[[Session], LLMGateway],
    http_client: httpx.Client,
    tavily: TavilyClient,
    *,
    limit: int = 10,
    budget_limit_usd=None,
) -> ResearchResult:
    from decimal import Decimal

    started_at = datetime.now(UTC)
    run = StageRun(
        stage=RESEARCH_STAGE,
        entity_id=uuid.uuid5(_ENTITY_NAMESPACE, RESEARCH_STAGE),
        input_hash=_sha(f"{PROMPT_VERSION}|{limit}|{started_at.isoformat()}"),
        stage_config_hash=_sha(PROMPT_VERSION),
        status=StageRunStatus.RUNNING,
    )
    session.add(run)
    session.commit()
    run_id = run.id

    considered = researched = needs_more_info = failed = 0
    limit_usd = budget_limit_usd or Decimal("0.50")

    with correlation_id(str(run_id)):
        cards = _accepted_cards_without_package(session, limit)
        for card in cards:
            considered += 1
            budget = Budget(scope=BudgetScope.TOPIC, limits=BudgetLimits(max_cost_usd=limit_usd))
            gateway = gateway_factory(session, budget)
            package = ResearchPackageRow(card_id=card.id, status="researching")
            session.add(package)
            try:
                documents: list[ResearchDocument] = []
                texts: list[str] = []

                # The card's own source is on the linked Signal; look it up for the real URL.
                from signalforge.db.models import Signal

                signal = session.get(Signal, card.signal_id)
                primary_url = signal.canonical_url if signal else ""
                primary_text = _fetch_text(http_client, primary_url) if primary_url else None

                if primary_text is None:
                    package.status = "needs_more_info"
                    needs_more_info += 1
                    session.commit()
                    continue

                documents.append(
                    ResearchDocument(
                        url=primary_url, title=signal.title if signal else "",
                        source_label=signal.source if signal else "", is_primary=True,
                        raw_text_ref=f"inline://{card.id}/0",
                    )
                )
                texts.append(primary_text)

                secondary = tavily.search(card.what_happened, max_results=SECONDARY_SOURCE_CAP)
                for result in secondary:
                    text = _fetch_text(http_client, result.url)
                    if text is None:
                        continue
                    documents.append(
                        ResearchDocument(
                            url=result.url, title=result.title, source_label=result.url,
                            is_primary=False, raw_text_ref=f"inline://{card.id}/{len(documents)}",
                        )
                    )
                    texts.append(text)

                candidates: list[tuple[int, ResearchClaim]] = []
                for doc_index, text in enumerate(texts):
                    budget.check()
                    raw_claims = _extract_claims_for_document(gateway, run_id, text)
                    for raw in raw_claims:
                        if not span_exists(raw.evidence_span, text):
                            continue
                        candidates.append(
                            (
                                doc_index,
                                ResearchClaim(
                                    text=raw.text, evidence_span=raw.evidence_span,
                                    document_indices=(doc_index,),
                                ),
                            )
                        )

                merged = merge_claims(candidates)
                package.documents = [d.model_dump(mode="json") for d in documents]
                package.claims = [c.model_dump(mode="json") for c in merged]

                if not merged:
                    package.status = "needs_more_info"
                    needs_more_info += 1
                else:
                    package.status = "researched"
                    researched += 1
                session.commit()
            except BudgetExceededError:
                package.status = "failed"
                failed += 1
                session.commit()
            except (RetryableError, PermanentError) as exc:
                log.warning("research failed", extra={"card_id": str(card.id), "error": str(exc)})
                package.status = "failed"
                failed += 1
                session.commit()

    run.status = StageRunStatus.SUCCEEDED
    session.commit()
    return ResearchResult(considered, researched, needs_more_info, failed, run_id)
```

Before wiring this up, verify against the actual `TopicCardRow`/`Signal` column names (`signal.canonical_url`, `signal.title`, `signal.source`) by reading `db/models/signals.py` and `db/models/cards.py`. Also verify `LLMGateway.complete_json`'s exact signature against `llm/gateway.py` (it is `complete_json(*, role, system, user, schema, stage_run_id)`, confirmed in this plan's research — matches the sketch above) and `core/logging.correlation_id`'s and `stages/ingest._ENTITY_NAMESPACE`/`_sha`'s real signatures before use, since this task only read them in passing while writing the plan.

- [ ] **Step 4: Fix the implementation against the real signatures found above, then run tests**

Run: `uv run pytest tests/stages/test_research.py -v`
Expected: PASS. Iterate on the implementation (not the tests) until green.

- [ ] **Step 5: Commit**

```bash
git add src/signalforge/stages/research.py tests/stages/test_research.py
git commit -m "feat: add research stage orchestration"
```

---

### Task 6: Docs

**Files:**
- Modify: `.kiro/steering/tech.md` (document `TAVILY_API_KEY`, `trafilatura`, the `research_extraction` role, the research stage)
- Modify: `README.md` if it lists stages/pipeline steps

**Interfaces:** none (docs only).

- [ ] **Step 1: Update `.kiro/steering/tech.md`**

Add a short entry documenting: new env var `TAVILY_API_KEY` (never printed), new dependency `trafilatura`, new LLM role `research_extraction`, new stage `research` (`stages/research.py`, `run_research`), new table `research_packages`. Follow the file's existing entry style and placement (alongside where `EDITOR_API_KEY`/other env vars are documented).

- [ ] **Step 2: Update `README.md` if it enumerates pipeline stages**

Run: `grep -n "assess\|cards stage\|ingest" README.md` first to see if such a list exists; if it does, add a `research` line in the same style; if not, skip this file.

- [ ] **Step 3: Commit**

```bash
git add .kiro/steering/tech.md README.md
git commit -m "docs: document the research stage and TAVILY_API_KEY"
```
