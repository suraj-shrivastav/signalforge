# SignalForge — Engineering Implementation Roadmap

**Objective:** Evolve SignalForge from an autonomous article-generation pipeline into a continuously improving, evidence-driven AI engineering newsroom.

**Guiding principles**
- Preserve Hermes' observe → decide → act → verify loop.
- Keep actions deterministic, idempotent and auditable.
- Evidence remains the source of truth.
- Humans remain responsible for ambiguous or high-risk decisions.
- Every improvement must have measurable acceptance criteria.
- No uncontrolled self-modification of production policies.

---

## Phase 0 — Establish the quality baseline

**Priority: P0 | Foundation**

Before adding features, measure what the existing system actually does.

### Tasks

- [ ] Define a common evaluation schema for every pipeline stage.
- [ ] Export representative historical cards, research results, drafts and decisions.
- [ ] Create a golden dataset of previously successful and failed cases.
- [ ] Label a subset of claims with human verification outcomes.
- [ ] Record baseline quality, latency and cost metrics.
- [ ] Version prompts, role mappings, rubrics and evaluation datasets.

### Metrics

- Grounded sentence rate
- Claim verification precision and recall
- Unsupported claim escape rate
- Research success rate
- Draft acceptance rate
- Cost per published article
- Time from signal to publication

**Deliverable:** Reproducible baseline evaluation suite.

---

## Phase 1 — Make the judge trustworthy

**Priority: P0 | Highest impact**

### 1.1 Human-calibrated judge

Build a human-labeled gold dataset for claim verification.

Implementation:
- Label claims as supported, partially supported, unsupported or unverifiable.
- Have at least two reviewers independently label a representative subset.
- Measure human-human agreement.
- Compare judge results against human labels.
- Calculate Cohen's kappa, precision, recall, F1 and confusion matrices.
- Keep a frozen holdout dataset.
- Recalibrate after changes to the judge model, prompt or rubric.

**Acceptance criteria:**
- Every judge version has a calibration report.
- Judge changes cannot silently bypass evaluation.
- Low-confidence and disputed claims enter human review.
- Judge performance is tracked across versions.

### 1.2 Independent evidence checker

Introduce an inexpensive NLI (Natural Language Inference) model.

Flow:

1. Extract claim and evidence span.
2. Run deterministic checks where possible.
3. Run NLI entailment/contradiction assessment.
4. Run the existing LLM judge.
5. Compare outcomes.
6. Escalate disagreements and uncertain results.

Do not treat NLI as ground truth. Validate it against the same human-labeled dataset.

### 1.3 Completeness and caveat verification

Add a separate editorial check.

Verify that:
- Important limitations are included.
- Benchmark configurations are accurately described.
- Experimental conditions are not omitted.
- Negative findings are preserved.
- Conclusions do not overstate the primary source.

**Deliverable:** A calibrated, multi-signal verification system.

---

## Phase 2 — Build Hermes' learning loop

**Priority: P0 | Biggest long-term opportunity**

### 2.1 Structured corrections memory

Create a persistent corrections database.

Suggested categories:
- factual_error
- missing_context
- unsupported_claim
- misleading_interpretation
- incorrect_number
- source_quality
- outdated_information
- editorial_quality

Each correction should store:
- Original article and claim
- Correction details
- Root cause
- Responsible pipeline stage
- Human or agent attribution
- Resolution
- Related entities and topics
- Timestamp

### 2.2 Contextual lessons retrieval

Avoid loading an ever-growing lessons.md into every prompt.

Instead:
- Retrieve relevant corrections by topic, entity and error category.
- Inject only relevant lessons into writer and judge context.
- Track which lessons influenced each decision.
- Version the correction and retrieval policies.

### 2.3 Outcome-based signal scoring

Capture editorial outcomes:
- Accepted or rejected
- Rejection reason
- Published or abandoned
- Human intervention
- Reader engagement
- Corrections after publication

Use this data to improve novelty and relevance scoring.

Important: Do not optimize for clicks alone. Include retention, usefulness, corrections and editorial quality.

**Safety:** Learned scoring changes must be evaluated offline and explicitly approved before production deployment.

**Deliverable:** Hermes can learn from historical editorial mistakes without silently rewriting its own rules.

---

## Phase 3 — Build story intelligence

**Priority: P0/P1 | Editorial efficiency**

### 3.1 Signal clustering and deduplication

Problem: One development may appear independently on GitHub, arXiv, Hacker News and RSS.

Implementation:
- Normalize titles and URLs.
- Generate embeddings.
- Calculate semantic similarity.
- Combine similarity with entity and timestamp matching.
- Use near-duplicate hashing for exact or almost-exact duplicates.
- Group related signals into a canonical story.
- Preserve every original source and its provenance.

Do not merge stories solely because their embeddings are similar.

### 3.2 Historical article matching

Before creating a new topic card:
- Search previous articles.
- Identify matching entities and topics.
- Compare the new signal against historical evidence.
- Classify it as duplicate, update, follow-up or genuinely new story.

### 3.3 Story lifecycle

Introduce story states:

- emerging
- researching
- published
- developing
- updated
- archived

Allow Hermes to revisit stories when new evidence emerges.

**Deliverable:** A newsroom that understands developments as evolving stories rather than isolated signals.

---

## Phase 4 — Continuous evaluation and CI

**Priority: P0 | Engineering reliability**

### 4.1 Golden cards in CI

Run representative golden cards against every important change.

Test:
- Signal assessment
- Novelty scoring
- Research extraction
- Evidence-span integrity
- Claim verification
- Revision behavior
- Final editorial decision

### 4.2 Regression gates

Suggested initial gates:

| Metric | Initial target |
|---|---:|
| Evidence references valid | 100% |
| Numeric checks passing | 100% |
| Unsupported claim escape | 0 in critical golden cases |
| Grounded sentence rate | No regression against baseline |
| Judge calibration | Meets approved human-agreement threshold |
| Budget enforcement | 100% |
| Idempotent action tests | 100% |

Treat these as initial engineering gates, not claims about current performance. Establish statistical confidence and adjust thresholds using actual production data.

### 4.3 Cost and latency regression

Track:
- Cost per pipeline stage
- Cost per published article
- Token usage
- Research retries
- Revision attempts
- Time to publish

**Deliverable:** Changes that reduce trustworthiness or increase cost unexpectedly are caught before deployment.

---

## Phase 5 — Editorial observability

**Priority: P1**

Build an internal Hermes operations dashboard.

### Funnel

Signals → Topic cards → Accepted → Researched → Drafted → Verified → Published

### Dashboard sections

1. Pipeline funnel and drop-off rates.
2. Rejection reasons.
3. Research failure rates.
4. Judge disagreement and human overrides.
5. Correction history.
6. Cost by model and pipeline stage.
7. Article quality trends.
8. Average time to publication.

Every decision should be drillable into its evidence and audit history.

**Deliverable:** A measurable view of newsroom performance.

---

## Phase 6 — Distribution and reader intelligence

**Priority: P1/P2**

### 6.1 Personalized digest

- Daily or weekly technical digest.
- Topic preferences.
- Topic muting.
- Story update notifications.
- RSS feed.
- Email subscription.

### 6.2 Reader feedback

Allow readers to:
- Report factual errors.
- Suggest missing context.
- Request deeper technical coverage.
- Rate article usefulness.

Feed verified feedback into the corrections and editorial learning loops.

### 6.3 Topic intelligence

Track:
- Emerging technologies.
- Fast-growing repositories.
- Research trends.
- Repeated benchmark improvements.
- Industry developments.

**Deliverable:** SignalForge becomes useful beyond the individual article.

---

# Recommended implementation sequence

| Sprint | Scope | Main output |
|---|---|---|
| 1 | Baseline + golden dataset | Evaluation foundation |
| 2 | Human-labeled judge calibration | Trustworthy judge |
| 3 | NLI + completeness checks | Better verification |
| 4 | Corrections database + retrieval | Editorial memory |
| 5 | Signal clustering | Duplicate reduction |
| 6 | Historical story matching | Story continuity |
| 7 | CI regression gates | Quality protection |
| 8 | Funnel dashboard | Operational visibility |
| 9 | Outcome-based scoring | Better editorial selection |
| 10 | Digest + reader feedback | Distribution loop |

Sprints are planning units, not fixed duration commitments. Adjust based on repository complexity and available engineering capacity.

---

# Suggested architecture additions

Keep the existing architecture. Add focused modules rather than creating a new agent framework.

```text
src/
├── evaluation/
│   ├── golden_dataset.py
│   ├── judge_calibration.py
│   ├── nli_checker.py
│   └── regression.py
│
├── memory/
│   ├── corrections.py
│   ├── lessons_retrieval.py
│   └── editorial_memory.py
│
├── intelligence/
│   ├── embeddings.py
│   ├── clustering.py
│   ├── deduplication.py
│   └── story_matching.py
│
├── analytics/
│   ├── funnel.py
│   ├── quality_metrics.py
│   └── cost_metrics.py
│
└── distribution/
    ├── digest.py
    ├── rss.py
    └── reader_feedback.py
```

Adapt these names to existing repository conventions rather than moving working modules unnecessarily.

### Database entities to consider

- `evaluation_runs`
- `golden_examples`
- `human_labels`
- `judge_calibrations`
- `corrections`
- `editorial_lessons`
- `story_clusters`
- `story_memberships`
- `article_relationships`
- `reader_feedback`

Use Alembic migrations and retain provenance, versioning and audit attribution.

---

# Definition of success

SignalForge should eventually demonstrate:

1. Its judge is measurably aligned with qualified human reviewers.
2. Corrections prevent recurring editorial mistakes.
3. Multiple sources about one development become one coherent story.
4. Previously published stories can evolve with new evidence.
5. Every major quality regression is detectable in CI.
6. Hermes can explain why it selected, rejected, revised or published a story.
7. Editorial quality improves without uncontrolled increases in cost or autonomy.

## Final engineering recommendation

Build these four things first:

1. **Judge Calibration**
2. **Corrections Memory**
3. **Story Clustering**
4. **Golden Dataset CI**

Do not start with newsletters, predictive analytics or additional autonomous agents.

The competitive advantage of SignalForge should not be that it publishes more articles. It should be that it consistently discovers important developments, verifies them rigorously and gets better at editorial decisions over time.
