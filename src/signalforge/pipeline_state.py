"""Where an accepted card is in the pipeline, and the one call that moves it forward."""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

# A card whose research failed or came back thin this many times is closed, not retried.
MAX_RESEARCH_ATTEMPTS: int = 2

# A card whose draft failed this many times is closed, not retried.
MAX_DRAFT_ATTEMPTS: int = 2

# The agent closes a card it cannot finish by rejecting it with this tag. Nothing waits on a
# person: the decision row records the actor, so an editor can still audit or reopen it.
CLOSE_REASON_TAG: str = "needs_more_evidence"


# review_log events that use up one redraft: a redraft that replaced the body, and one that
# failed and left it unchanged.
REDRAFT_EVENTS: frozenset[str] = frozenset({"redraft", "redraft_failed"})


def redrafts_used(review_log: Iterable[Mapping[str, Any]]) -> int:
    """Redrafts a draft has used, failed ones included (auto-review and classify share it)."""
    return sum(1 for event in review_log if event.get("type") in REDRAFT_EVENTS)


@dataclass(frozen=True)
class CardState:
    stage: str
    next_action: str


def classify(
    *,
    research: str | None,
    draft: str | None,
    review: str | None,
    published: str | None,
    has_cover: bool,
    has_figure: bool,
    max_redrafts: int,
    research_attempts: int = 0,
    draft_attempts: int = 0,
    redrafts: int = 0,
) -> CardState:
    """Pure mapping from stored statuses to a stage and the next action for the agent.

    ``redrafts`` is ``redrafts_used`` of the draft's review log; ``max_redrafts`` is the
    AUTO_REVIEW_MAX_REDRAFTS setting. A revise that has used them all is closed.
    """
    if research is None:
        return CardState("accepted", "run_research")
    if research == "researching":
        return CardState("researching", "wait")
    if research in ("failed", "needs_more_info") and research_attempts >= MAX_RESEARCH_ATTEMPTS:
        return CardState("research_parked", "close")
    if research in ("failed", "needs_more_info"):
        return CardState(f"research_{research}", "retry_research")
    if draft is None:
        return CardState("researched", "run_draft")
    if draft == "failed" and draft_attempts >= MAX_DRAFT_ATTEMPTS:
        return CardState("draft_failed", "close")
    if draft == "failed":
        return CardState("draft_failed", "retry_draft")
    if draft == "drafting":
        return CardState("draft_drafting", "wait")
    if draft != "drafted":
        return CardState(f"draft_{draft}", "close")
    if review == "pending":
        return CardState("awaiting_review", "auto_review")
    if review == "revise" and redrafts >= max_redrafts:
        return CardState("revise_exhausted", "close")
    if review == "revise":
        return CardState("revise_requested", "run_revise")
    if review == "rejected":
        return CardState("rejected", "none")
    if published == "unpublished":
        # The owner took it down. Only an editor publish brings it back.
        return CardState("unpublished", "none")
    if published != "published":
        return CardState("approved", "publish")
    if not (has_cover and has_figure):
        return CardState("published", "attach_images")
    return CardState("complete", "none")
