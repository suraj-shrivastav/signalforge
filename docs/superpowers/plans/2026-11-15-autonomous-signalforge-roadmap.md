# Autonomous SignalForge Implementation Plan

Status 2026-11-15: Milestone 1 merged (#136-#148); soak pending. Record: docs/pipeline/m1-autonomy-implementation.md

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Run SignalForge end to end with no human at runtime: off the laptop, never waiting on a person, able to stop itself, and verifying claims well enough that publishing without a human is safe.

**Architecture:** Keep the existing stages, the `pipeline_state.classify` state machine, the idempotent `/agent/*` API and the role map. Add a small control plane: a singleton `pipeline_controls` row (pause flag, slot lease), webhook alerts, real budgets, and a Python autopilot that a cloud cron runs every 15 minutes in place of launchd. Later milestones raise verification quality (persisted verdicts, synthetic and silver labels, a cross-family judge, canaries and breakers), then add offline gates, a same-news guard, post-publish re-verification and champion/challenger promotion.

**Tech Stack:** Python 3.13, uv, FastAPI, SQLAlchemy 2, Alembic, Postgres + pgvector (Supabase), httpx, pytest, ruff, mypy, GitHub Actions, Render (API host and cron).

**Spec:** [2026-11-15-signalforge-improvement.md](../specs/2026-11-15-signalforge-improvement.md) (the improvement roadmap). This plan departs from it where the debate and the code showed it was wrong for this project. Every departure is in "Decisions" below.

## Global Constraints

- No human in the loop at runtime. No `next_action` may wait on a person. A human may still pause, resume or audit, but nothing requires them to.
- The runtime agent never edits its own gates. Thresholds live in code constants or `Settings`, so changing one needs a PR on a protected branch.
- Every write the agent makes keeps its `actor` (`agent` or `editor`). Every LLM call is recorded in `llm_calls` with its cost.
- No LLM keys in GitHub Actions. CI runs only deterministic gates and offline replays.
- The autopilot holds only the revocable agent key. It has no database or storage credentials.
- Migrations are sequential and reversible (ADR-0004). The next free revision is `0013`. `alembic check` must stay clean.
- Run `uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pytest` before every commit.
- Commits and PRs are made as `suraj-shrivastav` and carry no Claude attribution lines (owner rule).
- Never commit `.agents/` or `docs/superpowers/specs/2026-10-01-article-drafting-research.md`.

---

## 1. What the code says (corrected facts)

These facts override the spec and the product summary where they disagree.

| Claim in spec or summary | What the code does | Evidence |
|---|---|---|
| The system refuses to run if writer and judge share a model family | It logs a warning and continues. Writer and judge are both `nvidia/` Nemotron. | `src/signalforge/stages/draft.py:542-548`; `README.md:59` and `ARCHITECTURE.md:102` are wrong |
| The judge is good enough to publish unattended | 8 of 24 invented clauses (33%) were accepted. Changed numbers: 0 of 16. False rejects: 2 of 24. | `docs/pipeline/eval-baseline-2026-10-21.json` (`neg`=40 is 16 number + 24 fabrication) |
| Cost is logged and each card has a budget | Prices are `None` for every role, so cost is 0 and the $1.50 cap can never trip. `BudgetLimits.max_calls` exists but config never sets it. | `src/signalforge/llm/roles.py:14-15,24-30`; `src/signalforge/core/config.py:174-180`; `src/signalforge/core/budget.py:46` |
| Hard cases go to a human | `draft != "drafted"` returns `human_review` (this includes `drafting`, a run still in progress). `parked` waits for the owner. | `src/signalforge/pipeline_state.py:31-40` |
| Autonomous scheduling | launchd on a laptop runs `scripts/hermes/*.sh`, and the slot state is a file in `$HOME`. Stage runs are daemon threads, so a restart leaves `researching`/`drafting` rows stuck and `classify` says `wait` forever. | `scripts/hermes/signalforge_cron_tick.sh`; `apps/api/agent_runs.py` |
| A Phase 0 baseline is needed | It mostly exists: `apps/worker/eval_drafts.py` (export/run/judge, `judge_probe`), `scripts/eval_research.py`, a baseline report. That report was taken on `draft-v3`; the current prompt is `draft-v8`. `export_fixtures` exports only researched packages. | `apps/worker/eval_drafts.py`; `src/signalforge/stages/draft.py:73` |
| Clustering can reuse stored embeddings | No embedding is stored anywhere. Research embeddings are temporary, and `signals.entities` is never filled. | migration `0001`; `src/signalforge/stages/research.py` |
| CI runs integration tests | The migrations and integration job is commented out. Its stated reason is wrong, because GitHub service containers need no local Docker. | `.github/workflows/ci.yml:36-90` |
| Same-family judges are the only option | The writer already has its own endpoint (`LLM_WRITER_BASE_URL`, `NVIDIA_API`). The judge uses `LLM_BASE_URL`. Family is the model id's namespace, so a non-`nvidia/` model on any reachable endpoint is cross-family. | `src/signalforge/core/config.py:64-78`; `src/signalforge/llm/roles.py:29` |
| RSS is to be built | The Atom feed shipped in PR #95. | `SESSION_PROGRESS.md` |
| Reader engagement can drive scoring | `apps/web` has no analytics. | grep finds no analytics or tracking code in `apps/web` |

## 2. Decisions

These were settled by grilling the spec against the owner's goal of full autonomy, and by a skeptic/advocate debate. Both sides converged on items 1-12.

| # | Decision | Rejected alternative and why |
|---|---|---|
| 1 | **Milestone 1 makes the system unattended and stoppable** before any quality work: cloud cron, no human dead ends, pause flag, alerts, real budgets, stale-run sweep, CI migrations job. | Starting with judge calibration (spec Phase 1). A calibrated judge is useless while the pipeline still dies with the laptop and cannot be stopped. |
| 2 | **Scheduler: a host cron job runs `apps/worker/autopilot.py` every 15 min. It calls the existing idempotent `/agent/*` API.** Slot state and its lease live in Postgres (`pipeline_controls`). | Procrastinate (ADR-0003). It needs a session-mode connection that is unreachable from this network (IPv6-only direct host). Revisit if runs must survive a mid-stage API restart. |
| 3 | **Dead ends become a terminal `close` action.** The agent rejects the card with reason tag `needs_more_evidence` and a note. `drafting` maps to `wait`. | A 7-day parked expiry: that is still a wait with nobody to act. One extra redraft: `needs_more_info` means research was thin, so a redraft cannot fix it. |
| 4 | **Ground truth without humans:** labels known by construction (synthetic negatives, scaled to ≥300 from ≥20 packages, with more mutation types) are the anchor. **Silver labels** come from a stronger cross-family `claim_referee`. They count only while the referee passes ≤2% false accept on the synthetic set. | Two human reviewers and kappa (spec 1.1). There is one operator, and the owner wants no runtime human. |
| 5 | **Persist every judge verdict** (`sentence_verdicts`). Today `_judge` throws accepted verdicts away, so there is nothing to calibrate against. | Calibrating from flags only. |
| 6 | **The judge gate to publish unattended:** fabrication false-accept ≤10%, with the 95% upper bound reported. Changed-number false-accept 0%. False-reject ≤10%. The target is ≤5% fabrication false-accept, reached with a jury on disagreement. Once a cross-family judge passes, the family check refuses again. | Shipping on the current 33% judge. |
| 7 | **No NLI model.** A second cross-family judge votes only when span check, judge or reorder disagree. Any reject flags the sentence. | NLI (spec 1.2). It is too heavy for the API host and still needs calibration. |
| 8 | **Circuit breakers auto-pause publishing.** They fire on: a per-batch canary of planted negatives that the judge accepts; a flagged share above baseline + 2 SD; 3 auto-review rejects in a row; a budget cap hit. A breaker pause has a cooldown (`paused_until`). The autopilot resumes only after the canary passes again. A manual pause has no expiry. | Human approval to resume (conflicts with autonomy). |
| 9 | **CI gates are deterministic:** recorded-reply cassettes through span check, number check and auto-review. A test fails when `PROMPT_VERSION` or the judge model has no committed eval report. The live eval runs nightly from the cron host and writes a dated report. | Live golden runs in CI (no keys, cost, a flaky gate). |
| 10 | **Same-news guard at accept time:** `signals.embedding` plus an identifier match (arXiv id, repo, host + normalised title), checked against 7 days of accepted cards and published articles. One card per cluster. | Six-state story lifecycle and three tables (spec 3.3). The real defect is narrow: "two accepted cards can cover the same news". |
| 11 | **Post-publish re-verification starts flag-only.** It auto-edits (`apply_sentence_edit` plus a correction note) only after 30 days with a false-flag rate ≤5%. | Auto-unpublish from day one. With today's judge it would flap. |
| 12 | **Champion/challenger promotes on the frozen offline set.** A 14-day shadow is a safety check only, not a statistical test (about 35 articles is too few). Promotion and rollback are rows in `policy_versions`. | Learned scoring promoted on production clicks. |
| 13 | **Deferred until ≥30 automatic corrections exist and analytics are installed:** lessons retrieval, outcome-based scoring, digest, personalisation, topic intelligence, reader feedback beyond an error-report form. | Spec Phases 2.2, 2.3 and 6 now. There is no data to learn from. |
| 14 | **No new `src/evaluation|memory|intelligence|analytics|distribution` trees.** Extend `apps/worker/eval_drafts.py`, `stages/`, `db/models/`, `db/repositories/` and `apps/api/routes/agent.py`. | The spec's proposed layout. It duplicates existing homes. |
| 15 | **Dashboard is an endpoint, not a UI:** `GET /agent/metrics` (funnel, breakers, cost). The Hermes evening report reads it. | A dashboard UI for one operator. |

## 3. Autonomy contract

What runs without a person, and the limits it runs inside.

- **Every 15 minutes** (cron): publish-next, images, close dead ends. If a 6-hour slot is due and its lease is free: tick, accept the top 2 cards, research, draft, auto-review, publish-next.
- **Nightly** (cron, from Milestone 2): live judge probe and canary refresh. From Milestone 5: re-verify published articles. Reports go to `docs/pipeline/` as artifacts, and alerts fire on regressions.
- **The agent may:** accept, close, review, revise, publish within the pace, pause itself, and resume after a breaker cooldown once the canary passes.
- **The agent may not:** change thresholds, prompts or models outside `policy_versions` promotion, publish while paused, or exceed per-card call/cost caps.
- **The kill switch:** `POST /agent/controls/pause` with either key. Every stage start and every publish checks it.
- **Alerts:** one webhook (`ALERT_WEBHOOK_URL`, Slack or Discord compatible). Fired on pause, on a breaker, and on a slot failed 3 times.

## 4. Milestones

| M | Name | Scope | Schema | Done when |
|---|---|---|---|---|
| 1 | Unattended and stoppable | Tasks 1-8 below | `0013 pipeline_controls` | 7 consecutive days with the laptop off: every slot runs or records why not, at least 2 publishes a day, no card in a non-terminal state for more than 24 h, and a pause stops publishing within one tick. CI runs migrations up/down and integration tests. |
| 2 | Trustworthy judge | Persist verdicts; grow `judge_probe` (negation flip, entity swap, unit swap, scope inflation, dropped hedge); `claim_referee` role; `eval_drafts calibrate` report (confusion matrix, kappa vs referee, CIs); pick the judge in an ADR; jury on disagreement; hard family check; canary in every judge batch; breakers. Fix `README.md:59` and `ARCHITECTURE.md:102`. | `0014 sentence_verdicts` (`id`, `draft_id`, `sentence`, `claim_ids` JSONB, `checker` in `span|judge|jury|referee|challenger|canary`, `model`, `prompt_version`, `supported` bool, `reason` text, `created_at`) | Judge gate from Decision 6 met on ≥300 synthetic negatives plus ≥500 silver sentences; each breaker trips once in a drill on the fake provider. |
| 3 | Offline gates | Cassettes `tests/golden/<id>.replies.json` replayed by `FakeProvider`; a version-gate test (`PROMPT_VERSION` and judge model must match the latest `docs/pipeline/eval-*.json`); export failed packages to the golden set too; re-baseline on the current prompt. | none | A PR that changes a prompt or judge model without a committed eval report fails CI. |
| 4 | Same-news guard | Embed signals in `stages/assess.py`; identifier match; `/cards/queue` returns one card per cluster; an already-published cluster ranks down as `already_covered`. Write an ADR that supersedes ADR-0006 on clustering. | `0015`: `signals.embedding vector(N)` + HNSW index; `topic_cards.cluster_id` (planned in ADR-0007) | 30-day replay: no same-news pair accepted (judged by the referee), at most 1 false skip. |
| 5 | Corrections and re-verify | Nightly `reverify` re-judges published sentences with the referee and re-fetches sources (drift vs `signals.content_hash`). It files corrections, flag-only at first. Unpublish and send-back require a category. Add an error-report form that queues a `reverify`. | `0016 corrections` (`id`, `published_article_id`, `sentence`, `category` from the spec list, `stage`, `detector`, `evidence`, `action` in `flagged|edited|unpublished|dismissed`, `actor`, `created_at`) | Every correction is categorised within 24 h. After 30 days, false-flag rate ≤5% enables auto-edit. |
| 6 | Champion/challenger | `policy_versions`; challengers run in shadow (`checker=challenger`). Promote on frozen-set wins. Roll back automatically when the correction rate or jury disagreement goes above the champion baseline. `GET /agent/metrics`. | `0017 policy_versions` (`id`, `kind` in `writer_prompt|judge|ranker_weights`, `version`, `config` JSONB, `status` in `champion|challenger|retired`, `metrics` JSONB, `promoted_at`, `rolled_back_at`) | One promotion and one forced rollback rehearsed end to end. |

Each of Milestones 2-6 gets its own detailed plan file when it starts. It is written against the data the earlier milestones produce, because writing them now would rot.

**Deferred (re-entry trigger in brackets):** lessons retrieval [≥30 corrections]; outcome-based scoring [≥30 corrections and analytics installed]; digest, email, personalisation, topic intelligence [analytics show readers]; story lifecycle states [follow-ups exceed 20% of accepted cards]; Procrastinate [mid-stage restarts lose work more than once a week].

---

## 5. Milestone 1: detailed tasks

### File map

| File | Change | Responsibility |
|---|---|---|
| `src/signalforge/pipeline_state.py` | Modify | `close` replaces `human_review` and `parked`; `drafting` waits |
| `tests/unit/test_pipeline_state.py` | Modify | New expectations, plus a property test that no action waits on a person |
| `src/signalforge/db/models/ops.py` | Modify | `PipelineControl` model |
| `src/signalforge/db/migrations/versions/0013_add_pipeline_controls.py` | Create | Table plus singleton row |
| `src/signalforge/db/repositories/controls.py` | Create | Pause, resume, slot claim and finish |
| `tests/integration/test_controls_repository.py` | Create | Repository behaviour on Postgres |
| `src/signalforge/control_policy.py` | Create | Pure functions: `is_paused`, `slot_id` |
| `tests/unit/test_control_policy.py` | Create | Pure logic tests |
| `apps/api/deps.py` | Modify | `get_controls_repository` |
| `apps/api/routes/agent.py` | Modify | `/agent/controls*` routes; pause guards |
| `tests/unit/test_api_controls.py` | Create | Routes and guards with a stub repository |
| `src/signalforge/alerts.py` | Create | Best-effort webhook alert |
| `tests/unit/test_alerts.py` | Create | Alert payload and failure handling |
| `src/signalforge/core/config.py` | Modify | `alert_webhook_url`, `llm_prices`, `budget_max_calls_*` |
| `src/signalforge/llm/roles.py` | Modify | Prices into `ModelSpec` |
| `tests/unit/test_config_budgets.py`, `tests/unit/test_llm_roles_prices.py` | Modify / Create | Budget and price tests |
| `src/signalforge/stale_runs.py` | Create | Sweep orphaned `running`/`researching`/`drafting` rows |
| `apps/api/main.py` | Modify | Run the sweep in `lifespan` |
| `tests/integration/test_stale_runs.py` | Create | Sweep behaviour |
| `apps/worker/autopilot.py` | Create | Python port of both cron scripts |
| `tests/unit/test_autopilot.py` | Create | Autopilot against `httpx.MockTransport` |
| `.github/workflows/ci.yml` | Modify | Restore the migrations and integration job |
| `docs/deploy-cron.md` | Create | Cron host setup and the soak checklist |
| `docs/pipeline/agent-api.md`, `ARCHITECTURE.md`, `README.md`, `scripts/hermes/evening-report-prompt.md` | Modify | `close`, cron and pause docs; family-check wording |

### Task 1: Terminal `close` action instead of human dead ends

**Files:**
- Modify: `src/signalforge/pipeline_state.py:30-40`
- Modify: `tests/unit/test_pipeline_state.py`
- Modify: `docs/pipeline/agent-api.md:26-27`, `ARCHITECTURE.md:66,86,106`, `scripts/hermes/evening-report-prompt.md:10`

**Interfaces:**
- Produces: `classify(...)` returns next_action `close` for `research_parked` and for `draft_needs_more_info`, and `wait` for `draft_drafting`. Constant `CLOSE_REASON_TAG = "needs_more_evidence"` in `pipeline_state.py`. Task 7 uses both.

- [ ] **Step 1: Update the failing expectations**

In `tests/unit/test_pipeline_state.py`, change the parametrize row for `needs_more_info` drafts, and add rows for `drafting` and the parked case:

```python
        ({"draft": "needs_more_info"}, ("draft_needs_more_info", "close")),
        ({"draft": "drafting", "review": None}, ("draft_drafting", "wait")),
```

Add these tests at the end of the file:

```python
from itertools import product

from signalforge.pipeline_state import CLOSE_REASON_TAG, MAX_RESEARCH_ATTEMPTS

# Every next_action the autopilot can execute without a person.
AUTONOMOUS_ACTIONS = {
    "run_research", "retry_research", "run_draft", "retry_draft", "auto_review",
    "run_revise", "publish", "attach_images", "close", "wait", "none",
}  # fmt: skip


def test_parked_research_closes() -> None:
    result = classify(
        research="failed", draft=None, review=None, published=None,
        has_cover=False, has_figure=False, research_attempts=MAX_RESEARCH_ATTEMPTS,
    )  # fmt: skip
    assert (result.stage, result.next_action) == ("research_parked", "close")


def test_no_action_waits_on_a_person() -> None:
    research = [None, "researching", "researched", "needs_more_info", "failed"]
    draft = [None, "drafting", "drafted", "needs_more_info", "failed"]
    review = [None, "pending", "approved", "revise", "rejected"]
    published = [None, "published", "unpublished"]
    for r, d, rv, p, cover, attempts in product(
        research, draft, review, published, [True, False], [0, MAX_RESEARCH_ATTEMPTS]
    ):
        action = classify(
            research=r, draft=d, review=rv, published=p,
            has_cover=cover, has_figure=cover, research_attempts=attempts,
        ).next_action  # fmt: skip
        assert action in AUTONOMOUS_ACTIONS, (r, d, rv, p, attempts, action)


def test_close_reason_tag_is_known() -> None:
    from signalforge.core.reason_tags import REASON_TAGS

    assert CLOSE_REASON_TAG in REASON_TAGS
```

Delete the old `parked` expectation if the file has one, because `test_parked_research_closes` replaces it.

- [ ] **Step 2: Run the tests and confirm they fail**

Run: `uv run pytest tests/unit/test_pipeline_state.py -v`
Expected: FAIL. You get `ImportError: cannot import name 'CLOSE_REASON_TAG'` until Step 3. After the import exists, the assertions fail on `human_review` and `parked`.

- [ ] **Step 3: Implement**

In `src/signalforge/pipeline_state.py`, add this constant under `MAX_RESEARCH_ATTEMPTS`:

```python
# The agent closes a card it cannot finish by rejecting it with this tag. Nothing waits on a
# person: the decision row records the actor, so an editor can still audit or reopen it.
CLOSE_REASON_TAG: str = "needs_more_evidence"
```

Replace the parked branch and the `draft != "drafted"` branch:

```python
    if research in ("failed", "needs_more_info") and research_attempts >= MAX_RESEARCH_ATTEMPTS:
        return CardState("research_parked", "close")
    ...
    if draft == "drafting":
        return CardState("draft_drafting", "wait")
    if draft != "drafted":
        return CardState(f"draft_{draft}", "close")
```

- [ ] **Step 4: Run the tests and confirm they pass**

Run: `uv run pytest tests/unit/test_pipeline_state.py tests/unit/test_reason_tags_sync.py -v`
Expected: PASS

- [ ] **Step 5: Update the docs that name the old actions**

In `docs/pipeline/agent-api.md`, replace the `human_review` and `parked` rows with:

```markdown
| `close` | the card cannot finish (research failed twice, or the draft had no usable claims). Reject it: `POST /cards/{id}/decision` with `{"decision":"rejected","reason_tags":["needs_more_evidence"],"note":"auto-closed: <stage>"}`. Never retry. |
```

In `ARCHITECTURE.md`, make three changes:
- Line 66: change the node label `parked` to `closed`.
- Line 86: replace "its `next_action` is `parked`; nothing retries it and the evening report lists it" with "its `next_action` is `close`: the agent rejects it with reason `needs_more_evidence`".
- Line 106: in the action list, remove `parked` and `human_review` and add `close`.

In `scripts/hermes/evening-report-prompt.md:10`, replace the line with: "List every card the agent closed today (decision `rejected`, note starting `auto-closed:`) by title."

Run: `grep -rn "human_review\|\"parked\"\|\`parked\`" src apps scripts docs ARCHITECTURE.md README.md`
Expected: no matches, apart from this plan and historical ADRs.

- [ ] **Step 6: Commit**

```bash
git add src/signalforge/pipeline_state.py tests/unit/test_pipeline_state.py docs/pipeline/agent-api.md ARCHITECTURE.md scripts/hermes/evening-report-prompt.md
git commit -m "feat: close dead-end cards instead of waiting on a person"
```

### Task 2: `pipeline_controls` table and repository

**Files:**
- Modify: `src/signalforge/db/models/ops.py` (append the model)
- Create: `src/signalforge/db/migrations/versions/0013_add_pipeline_controls.py`
- Create: `src/signalforge/control_policy.py`
- Create: `src/signalforge/db/repositories/controls.py`
- Test: `tests/unit/test_control_policy.py`, `tests/integration/test_controls_repository.py`

**Interfaces:**
- Produces: the model `PipelineControl`. Pure functions `is_paused(row, now) -> bool` and `slot_id(now_local: datetime) -> str` (for example `"2026-11-15-06"`). `ControlsRepository(session)` with `get() -> PipelineControl`, `pause(reason: str, actor: str, now: datetime, until: datetime | None = None) -> PipelineControl`, `resume(actor: str) -> PipelineControl`, `claim_slot(slot: str, now: datetime, lease: timedelta, max_failures: int = 3) -> SlotClaim`, and `finish_slot(slot: str, ok: bool) -> PipelineControl`. The dataclass `SlotClaim(claimed: bool, slot: str, failures: int)`.

- [ ] **Step 1: Write the failing pure-logic tests**

`tests/unit/test_control_policy.py`:

```python
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from signalforge.control_policy import is_paused, slot_id

NOW = datetime(2026, 11, 15, 7, 30, tzinfo=UTC)


def row(**kw: object) -> SimpleNamespace:
    return SimpleNamespace(**{"paused": False, "paused_until": None, **kw})


def test_not_paused() -> None:
    assert not is_paused(row(), NOW)  # type: ignore[arg-type]


def test_manual_pause_has_no_expiry() -> None:
    assert is_paused(row(paused=True), NOW)  # type: ignore[arg-type]


def test_breaker_pause_expires() -> None:
    assert is_paused(row(paused=True, paused_until=NOW + timedelta(minutes=1)), NOW)  # type: ignore[arg-type]
    assert not is_paused(row(paused=True, paused_until=NOW - timedelta(minutes=1)), NOW)  # type: ignore[arg-type]


def test_slot_id_rounds_down_to_six_hours() -> None:
    assert slot_id(datetime(2026, 11, 15, 0, 0)) == "2026-11-15-00"
    assert slot_id(datetime(2026, 11, 15, 5, 59)) == "2026-11-15-00"
    assert slot_id(datetime(2026, 11, 15, 6, 0)) == "2026-11-15-06"
    assert slot_id(datetime(2026, 11, 15, 23, 59)) == "2026-11-15-18"
```

- [ ] **Step 2: Run the tests and confirm they fail**

Run: `uv run pytest tests/unit/test_control_policy.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'signalforge.control_policy'`

- [ ] **Step 3: Implement the pure policy**

`src/signalforge/control_policy.py`:

```python
"""Pure rules for the pipeline control row: is it paused, and which 6-hour slot is due."""

from datetime import datetime
from typing import Protocol

SLOT_HOURS = 6


class _Pausable(Protocol):
    paused: bool
    paused_until: datetime | None


def is_paused(row: _Pausable, now: datetime) -> bool:
    """A manual pause (no ``paused_until``) holds until resumed; a breaker pause expires."""
    if not row.paused:
        return False
    return row.paused_until is None or row.paused_until > now


def slot_id(now_local: datetime) -> str:
    """The 6-hour slot (00, 06, 12, 18 local) that ``now_local`` falls in."""
    hour = now_local.hour // SLOT_HOURS * SLOT_HOURS
    return f"{now_local:%Y-%m-%d}-{hour:02d}"
```

Run: `uv run pytest tests/unit/test_control_policy.py -v`
Expected: PASS

- [ ] **Step 4: Add the model**

Append to `src/signalforge/db/models/ops.py`. `Boolean` and `Integer` come from `sqlalchemy`; add them to the existing import:

```python
class PipelineControl(Base, TimestampsMixin):
    """One row (id 1): the kill switch and the 6-hour slot lease. Seeded by migration 0013."""

    __tablename__ = "pipeline_controls"
    __table_args__ = (
        CheckConstraint("id = 1", name="singleton"),
        CheckConstraint(
            "slot_status IS NULL OR slot_status IN ('running', 'done', 'failed')",
            name="slot_status_allowed",
        ),
        CheckConstraint("slot_failures >= 0", name="slot_failures_non_negative"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    paused: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    paused_reason: Mapped[str | None] = mapped_column(Text, default=None)
    paused_by: Mapped[str | None] = mapped_column(String(32), default=None)
    paused_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    # Set by a circuit breaker: the pause lifts by itself after this. NULL for a manual pause.
    paused_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    slot: Mapped[str | None] = mapped_column(String(16), default=None)
    slot_status: Mapped[str | None] = mapped_column(String(16), default=None)
    slot_failures: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    slot_lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
```

Add `text` to the `sqlalchemy` import if it is missing. Export `PipelineControl` from `src/signalforge/db/models/__init__.py` the same way the file exports `StageRun`.

- [ ] **Step 5: Write migration 0013**

`src/signalforge/db/migrations/versions/0013_add_pipeline_controls.py`:

```python
"""add pipeline controls (kill switch and slot lease)

Revision ID: 0013
Revises: 0012
Create Date: 2026-11-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    table = op.create_table(
        "pipeline_controls",
        sa.Column("id", sa.Integer(), autoincrement=False, nullable=False),
        sa.Column("paused", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("paused_reason", sa.Text(), nullable=True),
        sa.Column("paused_by", sa.String(length=32), nullable=True),
        sa.Column("paused_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("paused_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("slot", sa.String(length=16), nullable=True),
        sa.Column("slot_status", sa.String(length=16), nullable=True),
        sa.Column("slot_failures", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("slot_lease_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("id = 1", name=op.f("ck_pipeline_controls_singleton")),
        sa.CheckConstraint(
            "slot_status IS NULL OR slot_status IN ('running', 'done', 'failed')",
            name=op.f("ck_pipeline_controls_slot_status_allowed"),
        ),
        sa.CheckConstraint(
            "slot_failures >= 0", name=op.f("ck_pipeline_controls_slot_failures_non_negative")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_pipeline_controls")),
    )
    # Seed the singleton so readers never race to create it.
    op.bulk_insert(table, [{"id": 1, "paused": False, "slot_failures": 0}])


def downgrade() -> None:
    op.drop_table("pipeline_controls")
```

The constraint names must match the naming convention in `src/signalforge/db/base.py`. Check them against the result of `uv run alembic revision --autogenerate -m probe` run on a database at 0012, then delete the probe file.

Run, against a throwaway or dev database: `uv run alembic upgrade head && uv run alembic check && uv run alembic downgrade 0012 && uv run alembic upgrade head`
Expected: no errors, and `alembic check` reports "No new upgrade operations detected."

- [ ] **Step 6: Write the failing repository tests**

`tests/integration/test_controls_repository.py`:

```python
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from signalforge.db.repositories.controls import ControlsRepository

NOW = datetime(2026, 11, 15, 6, 5, tzinfo=UTC)
LEASE = timedelta(hours=2)


def test_pause_and_resume_record_the_actor(db_session: Session) -> None:
    repo = ControlsRepository(db_session)
    row = repo.pause("canary failed", "agent", NOW, until=NOW + timedelta(hours=6))
    assert (row.paused, row.paused_by, row.paused_reason) == (True, "agent", "canary failed")
    row = repo.resume("editor")
    assert (row.paused, row.paused_until, row.paused_reason) == (False, None, None)


def test_claim_slot_once_until_finished(db_session: Session) -> None:
    repo = ControlsRepository(db_session)
    assert repo.claim_slot("2026-11-15-06", NOW, LEASE).claimed
    # A second run while the lease holds does not claim.
    assert not repo.claim_slot("2026-11-15-06", NOW + timedelta(minutes=15), LEASE).claimed
    repo.finish_slot("2026-11-15-06", ok=True)
    # A finished slot is not re-run.
    assert not repo.claim_slot("2026-11-15-06", NOW + timedelta(minutes=30), LEASE).claimed


def test_failed_slot_retries_until_max_failures(db_session: Session) -> None:
    repo = ControlsRepository(db_session)
    for attempt in range(3):
        claim = repo.claim_slot("2026-11-15-12", NOW, LEASE)
        assert claim.claimed and claim.failures == attempt
        repo.finish_slot("2026-11-15-12", ok=False)
    assert not repo.claim_slot("2026-11-15-12", NOW, LEASE).claimed


def test_expired_lease_can_be_reclaimed(db_session: Session) -> None:
    repo = ControlsRepository(db_session)
    assert repo.claim_slot("2026-11-15-18", NOW, LEASE).claimed
    assert repo.claim_slot("2026-11-15-18", NOW + LEASE + timedelta(seconds=1), LEASE).claimed


def test_new_slot_resets_failures(db_session: Session) -> None:
    repo = ControlsRepository(db_session)
    repo.claim_slot("2026-11-15-00", NOW, LEASE)
    repo.finish_slot("2026-11-15-00", ok=False)
    assert repo.claim_slot("2026-11-15-06", NOW, LEASE).failures == 0
```

Run: `TEST_DATABASE_URL=<throwaway db at head> uv run pytest tests/integration/test_controls_repository.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'signalforge.db.repositories.controls'`

- [ ] **Step 7: Implement the repository**

`src/signalforge/db/repositories/controls.py`:

```python
"""The pipeline control row: kill switch and 6-hour slot lease. Every call locks the row."""

from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from signalforge.db.models.ops import PipelineControl

SINGLETON_ID = 1


@dataclass(frozen=True)
class SlotClaim:
    claimed: bool
    slot: str
    failures: int


class ControlsRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self) -> PipelineControl:
        row = self._session.get(PipelineControl, SINGLETON_ID, with_for_update=True)
        if row is None:  # migration 0013 seeds it; a missing row is a broken database
            raise LookupError("pipeline_controls row 1 is missing; run alembic upgrade head")
        return row

    def pause(
        self, reason: str, actor: str, now: datetime, until: datetime | None = None
    ) -> PipelineControl:
        row = self.get()
        row.paused, row.paused_reason, row.paused_by = True, reason, actor
        row.paused_at, row.paused_until = now, until
        self._session.flush()
        return row

    def resume(self, actor: str) -> PipelineControl:
        row = self.get()
        row.paused, row.paused_reason, row.paused_until = False, None, None
        row.paused_by = actor
        self._session.flush()
        return row

    def claim_slot(
        self, slot: str, now: datetime, lease: timedelta, max_failures: int = 3
    ) -> SlotClaim:
        row = self.get()
        same = row.slot == slot
        failures = row.slot_failures if same else 0
        leased = row.slot_status == "running" and (
            row.slot_lease_until is not None and row.slot_lease_until > now
        )
        if leased or (same and row.slot_status == "done") or failures >= max_failures:
            return SlotClaim(False, slot, failures)
        row.slot, row.slot_status, row.slot_failures = slot, "running", failures
        row.slot_lease_until = now + lease
        self._session.flush()
        return SlotClaim(True, slot, failures)

    def finish_slot(self, slot: str, ok: bool) -> PipelineControl:
        row = self.get()
        if row.slot == slot:
            row.slot_status = "done" if ok else "failed"
            row.slot_failures += 0 if ok else 1
            row.slot_lease_until = None
            self._session.flush()
        return row
```

Run: `TEST_DATABASE_URL=<throwaway db at head> uv run pytest tests/integration/test_controls_repository.py -v`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add src/signalforge/control_policy.py src/signalforge/db/models/ops.py src/signalforge/db/models/__init__.py src/signalforge/db/migrations/versions/0013_add_pipeline_controls.py src/signalforge/db/repositories/controls.py tests/unit/test_control_policy.py tests/integration/test_controls_repository.py
git commit -m "feat: pipeline_controls row for the kill switch and slot lease"
```

### Task 3: Webhook alerts

**Files:**
- Create: `src/signalforge/alerts.py`
- Modify: `src/signalforge/core/config.py` (add the setting next to `agent_api_key`)
- Test: `tests/unit/test_alerts.py`

**Interfaces:**
- Produces: `send_alert(url: str | None, title: str, detail: str, *, client: httpx.Client | None = None) -> bool`. It never raises. Returns True when the webhook answered 2xx. Settings field `alert_webhook_url: SecretStr | None = None`.

- [ ] **Step 1: Write the failing test**

`tests/unit/test_alerts.py`:

```python
import json

import httpx

from signalforge.alerts import send_alert


def client(status: int, seen: list[httpx.Request]) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(status)

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_posts_slack_and_discord_compatible_payload() -> None:
    seen: list[httpx.Request] = []
    assert send_alert("https://hooks.example/x", "paused", "canary failed", client=client(200, seen))
    body = json.loads(seen[0].content)
    assert body["text"] == body["content"] == "[SignalForge] paused: canary failed"


def test_no_url_is_a_noop() -> None:
    assert send_alert(None, "paused", "x") is False


def test_failure_never_raises() -> None:
    seen: list[httpx.Request] = []
    assert send_alert("https://hooks.example/x", "t", "d", client=client(500, seen)) is False

    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down")

    broken = httpx.Client(transport=httpx.MockTransport(boom))
    assert send_alert("https://hooks.example/x", "t", "d", client=broken) is False
```

- [ ] **Step 2: Run the test and confirm it fails**

Run: `uv run pytest tests/unit/test_alerts.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'signalforge.alerts'`

- [ ] **Step 3: Implement**

`src/signalforge/alerts.py`:

```python
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
```

In `src/signalforge/core/config.py`, add this after `agent_api_key`:

```python
    # Incoming webhook (Slack or Discord) for pauses, breakers and failed slots. Unset: logs only.
    alert_webhook_url: SecretStr | None = None
```

If `tests/unit/test_log_extra_keys.py` restricts `extra` keys, add `title`, `error` and `status` to its allow-list.

- [ ] **Step 4: Run the tests and confirm they pass**

Run: `uv run pytest tests/unit/test_alerts.py tests/unit/test_config.py tests/unit/test_log_extra_keys.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/signalforge/alerts.py src/signalforge/core/config.py tests/unit/test_alerts.py tests/unit/test_log_extra_keys.py
git commit -m "feat: webhook alerts for pauses and failed slots"
```

### Task 4: Controls API and pause guards

**Files:**
- Modify: `apps/api/deps.py`
- Modify: `apps/api/routes/agent.py`
- Test: `tests/unit/test_api_controls.py`

**Interfaces:**
- Consumes: `ControlsRepository`, `SlotClaim`, `is_paused` (Task 2); `send_alert` and `Settings.alert_webhook_url` (Task 3).
- Produces these endpoints, all behind `require_editor_key`:
  - `GET /agent/controls` returns `ControlsOut{paused: bool, paused_reason, paused_by, paused_until, slot, slot_status, slot_failures}`.
  - `POST /agent/controls/pause` takes `{reason: str, minutes: int | None}` and returns `ControlsOut`. `minutes` set means a breaker pause.
  - `POST /agent/controls/resume` returns `ControlsOut`.
  - `POST /agent/controls/slot/claim` takes `{slot: str, lease_minutes: int = 120}` and returns `SlotClaimOut{claimed, slot, failures}`.
  - `POST /agent/controls/slot/finish` takes `{slot: str, ok: bool}` and returns `ControlsOut`.
  - `POST /agent/run/{stage}` and `POST /agent/publish-next` return **423** while paused. `auto-review?publish=true` still reviews while paused, but approves without publishing (`queued=true`).

- [ ] **Step 1: Write the failing tests**

`tests/unit/test_api_controls.py`:

```python
from collections.abc import Iterator
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest
from apps.api.deps import get_controls_repository
from apps.api.main import create_app
from fastapi.testclient import TestClient

from signalforge.core.config import Settings
from signalforge.db.repositories.controls import SlotClaim

DSN = "postgresql://u:p@localhost:5432/db"
KEY = "editor-secret-value"
H = {"X-Editor-Key": KEY}


class StubControls:
    def __init__(self) -> None:
        self.row = SimpleNamespace(
            paused=False, paused_reason=None, paused_by=None, paused_until=None,
            slot=None, slot_status=None, slot_failures=0,
        )  # fmt: skip
        self.claims: list[str] = []

    def get(self) -> Any:
        return self.row

    def pause(self, reason: str, actor: str, now: datetime, until: datetime | None = None) -> Any:
        self.row.paused, self.row.paused_reason, self.row.paused_by = True, reason, actor
        self.row.paused_until = until
        return self.row

    def resume(self, actor: str) -> Any:
        self.row.paused, self.row.paused_reason, self.row.paused_until = False, None, None
        return self.row

    def claim_slot(self, slot: str, now: datetime, lease: Any, max_failures: int = 3) -> SlotClaim:
        self.claims.append(slot)
        return SlotClaim(len(self.claims) == 1, slot, 0)

    def finish_slot(self, slot: str, ok: bool) -> Any:
        self.row.slot_status = "done" if ok else "failed"
        return self.row


@pytest.fixture
def ctx() -> Iterator[tuple[TestClient, StubControls]]:
    app = create_app(Settings(_env_file=None, database_url=DSN, editor_api_key=KEY))  # type: ignore[call-arg,arg-type]
    stub = StubControls()
    app.dependency_overrides[get_controls_repository] = lambda: stub
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client, stub


def test_pause_records_actor_and_resume_clears(ctx: tuple[TestClient, StubControls]) -> None:
    client, stub = ctx
    r = client.post("/agent/controls/pause", json={"reason": "drill"}, headers=H)
    assert r.status_code == 200 and r.json()["paused"] is True
    assert stub.row.paused_by == "editor" and stub.row.paused_until is None
    assert client.post("/agent/controls/resume", headers=H).json()["paused"] is False


def test_breaker_pause_sets_expiry(ctx: tuple[TestClient, StubControls]) -> None:
    client, stub = ctx
    client.post("/agent/controls/pause", json={"reason": "canary", "minutes": 360}, headers=H)
    assert stub.row.paused_until is not None and stub.row.paused_until > datetime.now(UTC)


def test_paused_blocks_stage_runs_and_publish(ctx: tuple[TestClient, StubControls]) -> None:
    client, stub = ctx
    stub.row.paused = True
    assert client.post("/agent/run/tick", headers=H).status_code == 423
    assert client.post("/agent/publish-next", headers=H).status_code == 423


def test_slot_claim_is_exclusive(ctx: tuple[TestClient, StubControls]) -> None:
    client, _ = ctx
    body = {"slot": "2026-11-15-06"}
    assert client.post("/agent/controls/slot/claim", json=body, headers=H).json()["claimed"]
    assert not client.post("/agent/controls/slot/claim", json=body, headers=H).json()["claimed"]


def test_controls_need_a_key(ctx: tuple[TestClient, StubControls]) -> None:
    client, _ = ctx
    assert client.get("/agent/controls").status_code in (401, 403)
```

- [ ] **Step 2: Run the tests and confirm they fail**

Run: `uv run pytest tests/unit/test_api_controls.py -v`
Expected: FAIL with `ImportError: cannot import name 'get_controls_repository'`

- [ ] **Step 3: Add the dependency**

In `apps/api/deps.py`, add this next to `get_card_repository`:

```python
def get_controls_repository(request: Request) -> Iterator[ControlsRepository]:
    with session_scope(request.app.state.session_factory) as session:
        yield ControlsRepository(session)
```

Add the import: `from signalforge.db.repositories.controls import ControlsRepository`.

- [ ] **Step 4: Add the routes and guards**

In `apps/api/routes/agent.py`, add these imports:

```python
from apps.api.deps import get_controls_repository
from signalforge.alerts import send_alert
from signalforge.control_policy import is_paused
from signalforge.db.repositories.controls import ControlsRepository

Controls = Annotated[ControlsRepository, Depends(get_controls_repository)]
```

Add the schemas and routes:

```python
class ControlsOut(BaseModel):
    paused: bool
    paused_reason: str | None
    paused_by: str | None
    paused_until: datetime | None
    slot: str | None
    slot_status: str | None
    slot_failures: int


class PauseIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str = Field(min_length=1, max_length=500)
    # Set by a circuit breaker: the pause lifts by itself after this many minutes.
    minutes: int | None = Field(default=None, ge=1, le=7 * 24 * 60)


class SlotIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    slot: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}-(00|06|12|18)$")
    lease_minutes: int = Field(default=120, ge=10, le=720)


class SlotFinishIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    slot: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}-(00|06|12|18)$")
    ok: bool


class SlotClaimOut(BaseModel):
    claimed: bool
    slot: str
    failures: int


def _controls_out(row: Any) -> ControlsOut:
    return ControlsOut(
        paused=is_paused(row, datetime.now(UTC)), paused_reason=row.paused_reason,
        paused_by=row.paused_by, paused_until=row.paused_until, slot=row.slot,
        slot_status=row.slot_status, slot_failures=row.slot_failures,
    )  # fmt: skip


def _ensure_running(controls: ControlsRepository) -> None:
    if is_paused(controls.get(), datetime.now(UTC)):
        raise HTTPException(status_code=423, detail="Pipeline is paused")


@router.get("/controls", response_model=ControlsOut)
def get_controls(controls: Controls) -> ControlsOut:
    return _controls_out(controls.get())


@router.post("/controls/pause", response_model=ControlsOut)
def pause(body: PauseIn, request: Request, controls: Controls, background: BackgroundTasks) -> ControlsOut:
    now = datetime.now(UTC)
    until = now + timedelta(minutes=body.minutes) if body.minutes else None
    row = controls.pause(body.reason, request.state.actor, now, until=until)
    url = request.app.state.settings.alert_webhook_url
    background.add_task(
        send_alert, url.get_secret_value() if url else None, "paused", body.reason
    )
    return _controls_out(row)


@router.post("/controls/resume", response_model=ControlsOut)
def resume(request: Request, controls: Controls) -> ControlsOut:
    return _controls_out(controls.resume(request.state.actor))


@router.post("/controls/slot/claim", response_model=SlotClaimOut)
def claim_slot(body: SlotIn, controls: Controls) -> SlotClaimOut:
    claim = controls.claim_slot(body.slot, datetime.now(UTC), timedelta(minutes=body.lease_minutes))
    return SlotClaimOut(claimed=claim.claimed, slot=claim.slot, failures=claim.failures)


@router.post("/controls/slot/finish", response_model=ControlsOut)
def finish_slot(body: SlotFinishIn, controls: Controls) -> ControlsOut:
    return _controls_out(controls.finish_slot(body.slot, body.ok))
```

Add the guards:
- In `run_stage`, add the parameter `controls: Controls` and call `_ensure_running(controls)` as the first line of the body.
- In `publish_next`, add the parameter `controls: Controls` and call `_ensure_running(controls)` as the first line of the body.
- In `auto_review`, add the parameter `controls: Controls` and put `publish = publish and not is_paused(controls.get(), datetime.now(UTC))` as the first line of the body.

`request.state.actor` is set by `require_editor_key` in `apps/api/routes/cards.py:43`.

- [ ] **Step 5: Run the tests and confirm they pass**

Run: `uv run pytest tests/unit/test_api_controls.py tests/unit -q`
Expected: PASS. Existing agent-route tests that call `run_stage`, `publish_next` or `auto_review` need a `get_controls_repository` override returning an unpaused `StubControls`. Add it to their fixtures.

- [ ] **Step 6: Commit**

```bash
git add apps/api/deps.py apps/api/routes/agent.py tests/unit/test_api_controls.py tests/unit
git commit -m "feat: kill switch and slot lease endpoints; stage runs and publish honour pause"
```

### Task 5: Real budgets (prices and call caps)

**Files:**
- Modify: `src/signalforge/core/config.py:120-125,174-180`
- Modify: `src/signalforge/llm/roles.py:24-30`
- Test: `tests/unit/test_config_budgets.py`, create `tests/unit/test_llm_roles_prices.py`

**Interfaces:**
- Produces: `Settings.llm_prices: dict[str, ModelPrice]`, where `ModelPrice` has `input: Decimal` and `output: Decimal` in USD per million tokens, keyed by model id and set from the env var `LLM_PRICES` as JSON. Also `Settings.budget_max_calls_per_topic: int | None = 40` and `Settings.budget_max_calls_per_article: int | None = 60`. `budget_limits(scope)` returns `max_calls`. `build_roles` fills `input_usd_per_mtok` and `output_usd_per_mtok`. `unpriced_models(roles) -> list[str]`.

- [ ] **Step 1: Measure the real call counts before choosing caps**

Run against production (read-only):

```sql
SELECT percentile_cont(0.95) WITHIN GROUP (ORDER BY n) AS p95, max(n)
FROM (SELECT sr.entity_id, count(*) AS n
      FROM llm_calls c JOIN stage_runs sr ON sr.id = c.stage_run_id
      WHERE sr.stage IN ('research', 'draft') AND c.created_at > now() - interval '30 days'
      GROUP BY sr.entity_id) t;
```

Set each default cap to about 2 × p95, rounded up. If the result differs a lot from 40/60, change the defaults in Step 3 and in the tests.

- [ ] **Step 2: Write the failing tests**

Append to `tests/unit/test_config_budgets.py`:

```python
from decimal import Decimal

from signalforge.core.budget import BudgetScope
from signalforge.core.config import Settings

DSN = "postgresql://u:p@localhost:5432/db"


def test_budget_limits_include_call_caps() -> None:
    s = Settings(_env_file=None, database_url=DSN, budget_max_calls_per_article=7)  # type: ignore[call-arg,arg-type]
    assert s.budget_limits(BudgetScope.ARTICLE).max_calls == 7
    assert s.budget_limits(BudgetScope.TOPIC).max_calls == 40


def test_llm_prices_parse_from_json_env(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("LLM_PRICES", '{"nvidia/x": {"input": "0.2", "output": "0.6"}}')
    s = Settings(_env_file=None, database_url=DSN)  # type: ignore[call-arg,arg-type]
    assert s.llm_prices["nvidia/x"].output == Decimal("0.6")
```

Create `tests/unit/test_llm_roles_prices.py`:

```python
from decimal import Decimal

from signalforge.core.config import Settings
from signalforge.llm.roles import build_roles, unpriced_models

DSN = "postgresql://u:p@localhost:5432/db"


def test_prices_flow_into_role_specs() -> None:
    s = Settings(
        _env_file=None, database_url=DSN, llm_model_claim_judge="google/j",
        llm_prices={"google/j": {"input": "1", "output": "2"}},
    )  # type: ignore[call-arg,arg-type]  # fmt: skip
    spec = build_roles(s)["claim_judge"]
    assert (spec.input_usd_per_mtok, spec.output_usd_per_mtok) == (Decimal("1"), Decimal("2"))
    assert "google/j" not in unpriced_models(build_roles(s))
    assert s.llm_model_article_writer in unpriced_models(build_roles(s))
```

Run: `uv run pytest tests/unit/test_config_budgets.py tests/unit/test_llm_roles_prices.py -v`
Expected: FAIL. Pydantic raises `ValidationError` for the unknown fields, and the import of `unpriced_models` fails.

- [ ] **Step 3: Implement**

In `src/signalforge/core/config.py`, add a model above `Settings`:

```python
class ModelPrice(BaseModel):
    """USD per million tokens. Set every model in use, or cost reads 0 and caps never trip."""

    input: Decimal = Field(ge=0)
    output: Decimal = Field(ge=0)
```

Import `BaseModel` from `pydantic` if it is not already imported. Add these fields next to `budget_per_article_usd`:

```python
    # Keyed by model id. Env: LLM_PRICES='{"vendor/model": {"input": "0.2", "output": "0.6"}}'.
    llm_prices: dict[str, ModelPrice] = Field(default_factory=dict)
    # Call caps: they trip even when a provider's price is unknown. Set from the p95 of real runs.
    budget_max_calls_per_topic: int | None = Field(default=40, ge=1)
    budget_max_calls_per_article: int | None = Field(default=60, ge=1)
```

Replace `budget_limits`:

```python
    def budget_limits(self, scope: BudgetScope) -> BudgetLimits:
        """Configured caps for a scope, so limits live in config rather than in stages."""
        caps = {
            BudgetScope.TOPIC: (self.budget_per_topic_usd, self.budget_max_calls_per_topic),
            BudgetScope.ARTICLE: (self.budget_per_article_usd, self.budget_max_calls_per_article),
        }
        cost, calls = caps[scope]
        return BudgetLimits(max_cost_usd=cost, max_calls=calls)
```

In `src/signalforge/llm/roles.py`, thread the prices through:

```python
def _spec(
    model: str,
    prices: Mapping[str, ModelPrice],
    max_output_tokens: int | None = None,
    timeout_s: float | None = None,
) -> ModelSpec:
    family = model.split("/", 1)[0] if "/" in model else "unknown"
    price = prices.get(model)
    return ModelSpec(
        model, family,
        input_usd_per_mtok=price.input if price else None,
        output_usd_per_mtok=price.output if price else None,
        max_output_tokens=max_output_tokens, timeout_s=timeout_s,
    )  # fmt: skip


def unpriced_models(roles: RoleMap) -> list[str]:
    """Model ids with no configured price: their cost reads 0."""
    return sorted({s.model_id for s in roles.values() if s.input_usd_per_mtok is None})
```

In `build_roles`, pass `settings.llm_prices` as the second argument of every `_spec(...)` call. Import `Mapping` from `collections.abc` and `ModelPrice` from `signalforge.core.config`. In `build_gateway` (`src/signalforge/llm/gateway.py`), log one warning at startup listing `unpriced_models(roles)` when that list is not empty.

- [ ] **Step 4: Run the tests and confirm they pass**

Run: `uv run pytest tests/unit/test_config_budgets.py tests/unit/test_llm_roles_prices.py tests/unit/test_budget.py tests/unit/test_llm_gateway.py -v`
Expected: PASS

- [ ] **Step 5: Set production values**

Add `LLM_PRICES` (the provider's list prices for each model in the role map) and the measured call caps to the API host's environment and to `scripts/hermes/signalforge.env.example`. Do not put real values in the repo.

- [ ] **Step 6: Commit**

```bash
git add src/signalforge/core/config.py src/signalforge/llm/roles.py src/signalforge/llm/gateway.py tests/unit/test_config_budgets.py tests/unit/test_llm_roles_prices.py scripts/hermes/signalforge.env.example
git commit -m "feat: model prices and call caps so per-card budgets can trip"
```

### Task 6: Sweep runs orphaned by a restart

**Files:**
- Create: `src/signalforge/stale_runs.py`
- Modify: `apps/api/main.py:29-36`
- Test: `tests/integration/test_stale_runs.py`

**Interfaces:**
- Produces: `sweep_stale_runs(session: Session, now: datetime, older_than: timedelta = timedelta(minutes=90)) -> SweepResult(stage_runs: int, research: int, drafts: int)`. It sets `stage_runs.status='failed'` and `error='interrupted: process restarted'`. It also sets `research_packages.status='failed'` where status is `researching`, and `article_drafts.status='failed'` where status is `drafting`, each with `failure_reason='interrupted'`, for rows older than the cutoff. `classify` then gives `retry_research` or `retry_draft` instead of `wait` forever.

- [ ] **Step 1: Write the failing test**

`tests/integration/test_stale_runs.py`. Build rows with the same helpers that `tests/integration/test_research_repository.py` and `tests/integration/test_draft.py` use to create a card, a research package and a draft:

```python
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from signalforge.db.models.ops import StageRun, StageRunStatus
from signalforge.stale_runs import sweep_stale_runs

NOW = datetime(2026, 11, 15, 12, 0, tzinfo=UTC)


def _run(session: Session, started: datetime) -> StageRun:
    import uuid

    run = StageRun(
        stage="research", entity_id=uuid.uuid4(), input_hash=uuid.uuid4().hex,
        stage_config_hash="x", status=StageRunStatus.RUNNING, started_at=started,
    )  # fmt: skip
    session.add(run)
    session.flush()
    return run


def test_old_running_rows_fail_and_fresh_ones_stay(db_session: Session) -> None:
    old = _run(db_session, NOW - timedelta(hours=3))
    fresh = _run(db_session, NOW - timedelta(minutes=5))
    result = sweep_stale_runs(db_session, NOW)
    db_session.refresh(old)
    db_session.refresh(fresh)
    assert result.stage_runs >= 1
    assert old.status == StageRunStatus.FAILED and old.error == "interrupted: process restarted"
    assert fresh.status == StageRunStatus.RUNNING


def test_sweep_is_idempotent(db_session: Session) -> None:
    _run(db_session, NOW - timedelta(hours=3))
    sweep_stale_runs(db_session, NOW)
    assert sweep_stale_runs(db_session, NOW).stage_runs == 0
```

Add one test each for a `researching` package and a `drafting` draft older than 90 minutes. Each asserts `status == "failed"` and `failure_reason == "interrupted"` after the sweep. Build the rows the way `tests/integration/test_research_repository.py` and `tests/integration/test_draft.py` do, and set `updated_at` to `NOW - timedelta(hours=3)`.

Run: `TEST_DATABASE_URL=<db> uv run pytest tests/integration/test_stale_runs.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'signalforge.stale_runs'`

- [ ] **Step 2: Implement**

`src/signalforge/stale_runs.py`:

```python
"""Stage runs are daemon threads: a restart kills them and leaves 'running' rows behind.

Mark those rows failed so the state machine retries them instead of waiting forever.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import update
from sqlalchemy.orm import Session

from signalforge.db.models.article import ArticleDraftRow
from signalforge.db.models.ops import StageRun, StageRunStatus
from signalforge.db.models.research import ResearchPackageRow

INTERRUPTED = "interrupted"


@dataclass(frozen=True)
class SweepResult:
    stage_runs: int
    research: int
    drafts: int


def sweep_stale_runs(
    session: Session, now: datetime, older_than: timedelta = timedelta(minutes=90)
) -> SweepResult:
    cutoff = now - older_than
    runs = session.execute(
        update(StageRun)
        .where(StageRun.status == StageRunStatus.RUNNING, StageRun.started_at < cutoff)
        .values(status=StageRunStatus.FAILED, finished_at=now, error=f"{INTERRUPTED}: process restarted")
    ).rowcount
    research = session.execute(
        update(ResearchPackageRow)
        .where(ResearchPackageRow.status == "researching", ResearchPackageRow.updated_at < cutoff)
        .values(status="failed", failure_reason=INTERRUPTED)
    ).rowcount
    drafts = session.execute(
        update(ArticleDraftRow)
        .where(ArticleDraftRow.status == "drafting", ArticleDraftRow.updated_at < cutoff)
        .values(status="failed", failure_reason=INTERRUPTED)
    ).rowcount
    session.commit()
    return SweepResult(runs or 0, research or 0, drafts or 0)
```

Check the column names `failure_reason` on both models (migrations 0008 and 0009). If either is named differently, use the real name.

In `apps/api/main.py` `lifespan`, after `app.state.session_factory = ...`, add:

```python
        # A restart kills in-flight stage threads; free their rows so cards retry (not wait).
        with app.state.session_factory() as session:
            result = sweep_stale_runs(session, datetime.now(UTC))
        if result.stage_runs or result.research or result.drafts:
            logging.getLogger(__name__).warning("swept stale runs", extra=asdict(result))
```

Add imports for `logging`, `asdict`, `datetime`, `UTC` and `sweep_stale_runs`. Also call `sweep_stale_runs` at the start of `apps/worker/autopilot.py:main` through the API: Task 7 calls `POST /agent/run/tick`, which runs after a restart anyway. The lifespan hook is the primary path.

- [ ] **Step 3: Run the tests and confirm they pass**

Run: `TEST_DATABASE_URL=<db> uv run pytest tests/integration/test_stale_runs.py -v && uv run pytest tests/unit -q`
Expected: PASS. Unit tests that build the app must not hit a database in `lifespan`. If `TestClient(app)` with a fake DSN now fails, wrap the sweep in `try/except SQLAlchemyError` that logs the error and continues. Startup must never fail on the sweep.

- [ ] **Step 4: Commit**

```bash
git add src/signalforge/stale_runs.py apps/api/main.py tests/integration/test_stale_runs.py
git commit -m "fix: fail stage rows orphaned by a restart so cards retry"
```

### Task 7: Autopilot (Python port of the cron scripts)

**Files:**
- Create: `apps/worker/autopilot.py`
- Test: `tests/unit/test_autopilot.py`

**Interfaces:**
- Consumes: the endpoints from Task 4, `next_action == "close"` and `CLOSE_REASON_TAG` from Task 1, and the existing `/agent/run/{stage}`, `/agent/runs`, `/agent/work`, `/cards/queue`, `/cards/{id}/decision`, `/agent/drafts/{id}/auto-review` and `/agent/publish-next`.
- Produces: `python -m apps.worker.autopilot`, with exit code 0 on success or skip and 1 on a failed slot. It reads these env vars: `API_BASE_URL`, `SIGNALFORGE_KEY` (agent key), `AUTOPILOT_TZ` (default `UTC`), `SITE_URL`, `REVALIDATE_SECRET`, `ALERT_WEBHOOK_URL`, `AUTOPILOT_ACCEPT_PER_RUN` (default 2). It never reads `DATABASE_URL`.

Behaviour, matching `scripts/hermes/signalforge_cron_tick.sh` and `signalforge_cron_pipeline.sh`:
1. `GET /agent/controls`. If paused, log and exit 0.
2. Publish tick: `POST /agent/publish-next`, and revalidate the site if something was published.
3. Images tick: run `skills/article-images/scripts/articleimg.py auto` as a subprocess with the same env. Failures are logged and never fail the run.
4. Close dead ends: for every `/agent/work` card with `next_action == "close"`, call `POST /cards/{id}/decision` with `rejected`, `[CLOSE_REASON_TAG]` and `note="auto-closed: <stage>"`.
5. `POST /agent/controls/slot/claim` with `slot_id(now in AUTOPILOT_TZ)`. If not claimed, exit 0.
6. Slot pipeline:
   - Run `tick` and wait for it.
   - Accept the top `AUTOPILOT_ACCEPT_PER_RUN` proposed cards from `/cards/queue?limit=50` (decision `accepted`, note `auto-accepted: topmost by score`).
   - Up to 2 passes: run research (`retry_failed=true`, limit = waiting cards clamped to 1-4) and wait; run draft (`retry_failed=true`) and wait. Stop early once a card shows `auto_review`.
   - For up to 3 `auto_review` cards: `auto-review?publish=true`. On `revise`, run `revise` and wait, then review again (at most 3 tries per card).
   - Finish with `publish-next`.
7. `POST /agent/controls/slot/finish` with `ok`. If the slot failed and `failures + 1 >= 3`, call `send_alert`.

`wait_stage` polls `/agent/runs` every 60 s, for at most 30 polls. A request error or a non-object body counts as "unknown", never as "finished". A 423 from any call means paused: finish the slot with `ok=false` and exit 0.

- [ ] **Step 1: Write the failing tests**

`tests/unit/test_autopilot.py`:

```python
import json
from collections.abc import Callable
from datetime import UTC, datetime

import httpx
import pytest
from apps.worker import autopilot

Handler = Callable[[httpx.Request], httpx.Response]


def api(routes: dict[tuple[str, str], object], calls: list[str]) -> autopilot.Api:
    def handler(request: httpx.Request) -> httpx.Response:
        key = (request.method, request.url.path)
        calls.append(f"{request.method} {request.url.path}")
        body = routes.get(key, {})
        if isinstance(body, int):
            return httpx.Response(body, json={})
        return httpx.Response(200, json=body)

    client = httpx.Client(base_url="https://api.test", transport=httpx.MockTransport(handler))
    return autopilot.Api(client, sleep=lambda _s: None)


UNPAUSED = {"paused": False, "paused_reason": None, "paused_by": None, "paused_until": None,
            "slot": None, "slot_status": None, "slot_failures": 0}  # fmt: skip


def test_paused_does_nothing() -> None:
    calls: list[str] = []
    a = api({("GET", "/agent/controls"): {**UNPAUSED, "paused": True}}, calls)
    assert autopilot.run_once(a, now=datetime(2026, 11, 15, 6, tzinfo=UTC), env={}) == 0
    assert calls == ["GET /agent/controls"]


def test_closes_dead_end_cards_with_reason_tag() -> None:
    calls: list[str] = []
    sent: list[dict[str, object]] = []
    card = {"card_id": "c1", "title": "t", "stage": "research_parked", "next_action": "close", "slug": None}

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(f"{request.method} {request.url.path}")
        if request.url.path == "/agent/work":
            return httpx.Response(200, json={"counts": {"close": 1}, "cards": [card]})
        if request.url.path == "/cards/c1/decision":
            sent.append(json.loads(request.content))
            return httpx.Response(201, json={})
        return httpx.Response(200, json={})

    client = httpx.Client(base_url="https://api.test", transport=httpx.MockTransport(handler))
    autopilot.close_dead_ends(autopilot.Api(client, sleep=lambda _s: None))
    assert sent == [{"decision": "rejected", "reason_tags": ["needs_more_evidence"],
                     "note": "auto-closed: research_parked"}]  # fmt: skip


def test_unclaimed_slot_skips_pipeline() -> None:
    calls: list[str] = []
    a = api(
        {
            ("GET", "/agent/controls"): UNPAUSED,
            ("GET", "/agent/work"): {"counts": {}, "cards": []},
            ("POST", "/agent/publish-next"): {"published": None, "waiting": 0, "next_publish_at": None},
            ("POST", "/agent/controls/slot/claim"): {"claimed": False, "slot": "s", "failures": 0},
        },
        calls,
    )
    assert autopilot.run_once(a, now=datetime(2026, 11, 15, 6, tzinfo=UTC), env={}) == 0
    assert "POST /agent/run/tick" not in calls


def test_wait_stage_treats_errors_as_unknown() -> None:
    replies = iter([httpx.Response(502), httpx.Response(200, json={"running": None, "last": {}})])
    client = httpx.Client(
        base_url="https://api.test", transport=httpx.MockTransport(lambda _r: next(replies))
    )
    assert autopilot.Api(client, sleep=lambda _s: None).wait_stage("tick") is True


def test_wait_stage_gives_up_after_max_polls() -> None:
    client = httpx.Client(
        base_url="https://api.test",
        transport=httpx.MockTransport(
            lambda _r: httpx.Response(200, json={"running": {"stage": "tick"}, "last": {}})
        ),
    )
    assert autopilot.Api(client, sleep=lambda _s: None).wait_stage("tick", polls=3) is False


@pytest.mark.parametrize("hour,slot", [(0, "2026-11-15-00"), (13, "2026-11-15-12")])
def test_slot_uses_configured_timezone(hour: int, slot: str) -> None:
    now = datetime(2026, 11, 15, hour, 30, tzinfo=UTC)
    assert autopilot.current_slot(now, "UTC") == slot
```

- [ ] **Step 2: Run the tests and confirm they fail**

Run: `uv run pytest tests/unit/test_autopilot.py -v`
Expected: FAIL with `ImportError: cannot import name 'autopilot'`

- [ ] **Step 3: Implement**

`apps/worker/autopilot.py`:

```python
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
from signalforge.pipeline_state import CLOSE_REASON_TAG

log = logging.getLogger("autopilot")
REPO = Path(__file__).resolve().parents[2]
_POLL_S = 60
_MAX_POLLS = 30


class Paused(Exception):
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
                raise Paused(path)
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
        httpx.post(f"{site.rstrip('/')}/api/revalidate", headers={"x-revalidate-secret": secret}, timeout=30)
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
    try:
        out = subprocess.run(
            [sys.executable, str(script), "auto"], env={**os.environ, **env},
            capture_output=True, text=True, timeout=600, check=False,
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
    return [c for c in api.call("GET", "/agent/work").get("cards", []) if c["next_action"] == action]


def accept_best_cards(api: Api, count: int) -> int:
    queue = api.call("GET", "/cards/queue", params={"limit": 50})
    items = queue if isinstance(queue, list) else queue.get("items", [])
    proposed = [i for i in items if i.get("status") == "proposed"]
    proposed.sort(key=lambda i: i.get("score") or 0, reverse=True)
    for item in proposed[:count]:
        api.call(
            "POST", f"/cards/{item['id']}/decision",
            json={"decision": "accepted", "note": "auto-accepted: topmost by score"},
        )  # fmt: skip
    return min(count, len(proposed))


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
    for card in _work(api, "auto_review")[:3]:
        for _ in range(3):
            body = api.call(
                "POST", f"/agent/drafts/{card['card_id']}/auto-review", params={"publish": "true"}
            )
            if isinstance(body.get("published"), dict):
                revalidate_site(env)
            if body.get("action") != "revise" or not api.start("revise"):
                break
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
    except Paused:
        log.info("paused mid-run")
        if claim.get("claimed"):  # never finish a slot another run holds
            api.call("POST", "/agent/controls/slot/finish", json={"slot": slot, "ok": False})
        return 0
    except (httpx.HTTPError, RuntimeError) as exc:
        log.error("slot %s aborted: %s", slot, exc)
        ok = False
        if not claim.get("claimed"):
            return 1
    api.call("POST", "/agent/controls/slot/finish", json={"slot": slot, "ok": ok})
    if not ok and claim.get("failures", 0) + 1 >= 3:
        send_alert(env.get("ALERT_WEBHOOK_URL"), "slot failed 3 times", slot)
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
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
```

Check `accept_best_cards` against the real `/cards/queue` response shape in `apps/api/routes/cards.py` (the list key, `id`, `status`, `score`). Fix the field names if they differ, and add a unit test with a captured real response.

- [ ] **Step 4: Run the tests and confirm they pass**

Run: `uv run pytest tests/unit/test_autopilot.py -v && uv run mypy`
Expected: PASS

- [ ] **Step 5: Dry run against staging or production with pause on**

Run `POST /agent/controls/pause {"reason":"autopilot dry run"}`, then `API_BASE_URL=... SIGNALFORGE_KEY=... uv run python -m apps.worker.autopilot`.
Expected: it logs "paused, nothing to do", exits 0, and changes nothing. Resume afterwards.

- [ ] **Step 6: Commit**

```bash
git add apps/worker/autopilot.py tests/unit/test_autopilot.py
git commit -m "feat: autopilot runs the slot pipeline from any cron host via the agent API"
```

### Task 8: CI migrations job, cron host, soak and decommission launchd

**Files:**
- Modify: `.github/workflows/ci.yml:36-90`
- Create: `docs/deploy-cron.md`
- Modify: `ARCHITECTURE.md` (§1 and §7), `README.md:59,122`

- [ ] **Step 1: Restore the migrations job**

Uncomment the `migrations` job in `.github/workflows/ci.yml`. Replace the comment above it with:

```yaml
  # Throwaway pgvector service container on the runner (no local Docker needed). CI never
  # touches Supabase.
```

Set `TEST_DATABASE_URL: postgresql://postgres:postgres@localhost:5432/postgres` next to `DATABASE_URL` in the job `env`. Make the last step:

```yaml
      - name: Integration tests
        run: uv run pytest tests/integration -v
```

Push the branch. Expected: both jobs are green. Any of the 17 known integration failures that still fail on an empty database are real bugs: fix them in this task, or mark them `xfail` with a linked issue. Never skip them silently.

- [ ] **Step 2: Write `docs/deploy-cron.md`**

The file covers:
- **Render Cron Job** from this repo with the API's build. Schedule `*/15 * * * *`, command `uv run python -m apps.worker.autopilot`. Env: `API_BASE_URL`, `SIGNALFORGE_KEY` (agent key), `AUTOPILOT_TZ` (the zone the laptop used), `SITE_URL`, `REVALIDATE_SECRET`, `ALERT_WEBHOOK_URL`. It needs no `DATABASE_URL` or storage keys.
- **Railway equivalent:** a cron service with the same command and env.
- **Soak checklist:** run the cron and launchd side by side for 1 day. The slot lease makes the second one a no-op. Check `slot_status=done` for each slot.
- **Decommission launchd:** `launchctl unload ~/Library/LaunchAgents/ai.signalforge.cron.plist`, and keep the scripts for one release as a fallback.
- **Kill switch drill:** pause, confirm the next tick does nothing, resume.

- [ ] **Step 3: Fix the docs that state false guarantees**

- `README.md:59`: change "refuses to run them on the same model family" to "warns when they share a model family (only NVIDIA-hosted models were reachable); Milestone 2 makes this a hard check again once a cross-family judge passes calibration".
- `README.md:122` and `ARCHITECTURE.md` §1: replace the launchd scheduler with the cron-hosted autopilot, and add the pause and alert paths.
- `ARCHITECTURE.md` §7: remove "Scheduling depends on the laptop being on".

- [ ] **Step 4: Run the full checks**

Run: `uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pytest`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add .github/workflows/ci.yml docs/deploy-cron.md ARCHITECTURE.md README.md
git commit -m "ci: restore migrations and integration job; docs: cron autopilot replaces launchd"
```

- [ ] **Step 6: Milestone 1 exit soak (7 days, laptop off)**

Check daily from the API, not the laptop:
- `GET /agent/controls` shows `slot_status=done` and `slot_failures=0` for every slot.
- At least 2 publishes per day.
- `GET /agent/work` has no card whose `stage` has stayed the same for more than 24 h.
- One kill-switch drill.
- One alert received.

Record the results in `docs/pipeline/m1-soak-<date>.md`. Milestone 2 starts only when the soak passes.

---

## 6. Self-review

- **Spec coverage:**
  - Phase 0 is covered by facts §1 and M3 (re-baseline, failed packages).
  - Phase 1.1 and 1.2 are covered by M2. NLI is replaced by a jury (Decision 7).
  - Phase 1.3 is covered by the M2 probe types (scope inflation, dropped hedge).
  - Phase 2.1 is covered by M5. Phases 2.2 and 2.3 are deferred, with triggers.
  - Phases 3.1 and 3.2 are covered by M4. Phase 3.3 is deferred.
  - Phase 4 is covered by Task 8 and M3. Cost regression is covered by Task 5.
  - Phase 5 is covered by `GET /agent/metrics` in M6. Phase 6 is deferred.
  - The spec's "humans remain responsible" principle is replaced by the autonomy contract (§3), at the owner's direction.
- **Placeholder scan:** each step names its exact file, command and expected output. The places that depend on unread code (the `/cards/queue` shape, `failure_reason` column names, the log extra-key allow-list) say what to check and how.
- **Type consistency:**
  - `SlotClaim(claimed, slot, failures)` is the same in Tasks 2, 4 and 7.
  - `is_paused(row, now)` is the same in Tasks 2 and 4.
  - `CLOSE_REASON_TAG` is the same in Tasks 1 and 7.
  - `send_alert(url, title, detail, *, client)` is the same in Tasks 3, 4 and 7.
