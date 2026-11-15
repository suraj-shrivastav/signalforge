"""Plain-English explanation of where one card is and why. Pure: no database, no LLM."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID

from signalforge.pipeline_state import MAX_DRAFT_ATTEMPTS, MAX_RESEARCH_ATTEMPTS, CardState

# After these states nothing more happens to the card, so a pause does not matter.
_SETTLED = frozenset({"none", "close"})


@dataclass(frozen=True)
class CardFacts:
    """Stored facts about one card, as the pipeline query returns them."""

    card_id: UUID
    title: str
    created_at: datetime
    decision: str | None
    research_status: str | None = None
    research_attempts: int = 0
    research_failure: str | None = None
    draft_status: str | None = None
    draft_attempts: int = 0
    draft_failure: str | None = None
    review_status: str | None = None
    review_log: Sequence[Mapping[str, Any]] = field(default_factory=tuple)
    published_status: str | None = None
    slug: str | None = None
    has_cover: bool = False
    has_figure: bool = False


def failure_class(reason: str | None) -> str | None:
    """The class prefix of a failure reason (``thin: ...`` gives ``thin``), else None."""
    if not reason or ":" not in reason:
        return None
    head = reason.split(":", 1)[0].strip()
    return head if head and " " not in head else None


def review_reasons(review_log: Sequence[Mapping[str, Any]], last: int = 3) -> list[str]:
    """The last ``last`` reasons recorded in the review log, oldest first."""
    out: list[str] = []
    for event in review_log:
        reasons = event.get("reasons")
        if isinstance(reasons, list | tuple):
            out.extend(str(r) for r in reasons if r)
        elif event.get("note"):
            out.append(str(event["note"]))
    return out[-last:]


def _times(n: int) -> str:
    return "twice" if n == 2 else f"{n} times"


def _ordinal(n: int) -> str:
    if 10 <= n % 100 <= 20:
        return f"{n}th"
    return f"{n}{ {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th') }"


def _with_class(text: str, reason: str | None) -> str:
    kind = failure_class(reason)
    return f"{text} ({kind})" if kind else text


def summarize(
    facts: CardFacts,
    state: CardState,
    *,
    paused_reason: str | None,
    max_redrafts: int,
    redrafts: int,
    queue_position: int | None = None,
    next_publish_at: datetime | None = None,
) -> str:
    """One sentence on where the card is. ``paused_reason`` is set only while paused."""
    if facts.decision is not None and facts.decision != "accepted":
        return f"Not accepted: the latest editor decision is {facts.decision}"
    stage, action = state.stage, state.next_action
    if stage == "unpublished":
        return "Unpublished by the owner"
    if stage in ("published", "complete"):
        base = "Published"
        return base if stage == "complete" else f"{base}; the cover and figure are still to attach"
    if paused_reason is not None and action not in _SETTLED:
        return f"Paused: {paused_reason}. It continues ({action}) once the pipeline resumes"
    reasons = review_reasons(facts.review_log, 1)
    last = f": {reasons[0]}" if reasons else ""
    if stage == "research_parked":
        verb = "failed" if facts.research_status == "failed" else "came back thin"
        text = f"Closed: research {verb} {_times(facts.research_attempts)}"
        return _with_class(text, facts.research_failure)
    if stage == "draft_failed" and action == "close":
        text = f"Closed: the draft failed {_times(facts.draft_attempts)}"
        return _with_class(text, facts.draft_failure)
    if stage == "revise_exhausted":
        return (
            f"Closed: the draft still failed review after {redrafts} of {max_redrafts} "
            f"redrafts{last}"
        )
    if action == "close":
        return "Closed: the draft had too few usable claims"
    if stage == "rejected":
        return f"Rejected in review{last}"
    if stage == "approved":
        if queue_position is None or next_publish_at is None:
            return "Approved; waiting for a publish slot"
        return (
            f"Waiting for the publish pace: next slot {next_publish_at:%H:%M} UTC, "
            f"{_ordinal(queue_position)} in queue"
        )
    if stage == "revise_requested":
        return f"Waiting for a redraft ({redrafts} of {max_redrafts} used){last}"
    if stage == "awaiting_review":
        return "Drafted; waiting for the automatic review"
    if stage == "research_failed" or stage == "research_needs_more_info":
        text = (
            f"Research did not finish (attempt {facts.research_attempts} of "
            f"{MAX_RESEARCH_ATTEMPTS}); it retries next run"
        )
        return _with_class(text, facts.research_failure)
    if stage == "draft_failed":
        text = (
            f"The draft failed (attempt {facts.draft_attempts} of "
            f"{MAX_DRAFT_ATTEMPTS}); it retries next run"
        )
        return _with_class(text, facts.draft_failure)
    return {
        "accepted": "Accepted; waiting for research to start",
        "researching": "Research is running now",
        "researched": "Researched; waiting for the draft to start",
        "draft_drafting": "The draft is being written now",
    }.get(stage, f"In stage {stage}; next action {action}")
