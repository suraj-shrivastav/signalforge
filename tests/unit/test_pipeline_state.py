from itertools import product

import pytest

from signalforge.pipeline_state import (
    CLOSE_REASON_TAG,
    MAX_DRAFT_ATTEMPTS,
    MAX_RESEARCH_ATTEMPTS,
    classify,
    redrafts_used,
)


def state(**kw: object) -> tuple[str, str]:
    base: dict[str, object] = {
        "research": "researched", "draft": "drafted", "review": "pending",
        "published": None, "has_cover": False, "has_figure": False, "max_redrafts": 2,
    }  # fmt: skip
    result = classify(**{**base, **kw})  # type: ignore[arg-type]
    return result.stage, result.next_action


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        ({"research": None, "draft": None, "review": None}, ("accepted", "run_research")),
        ({"research": "researching", "draft": None}, ("researching", "wait")),
        ({"research": "failed", "draft": None}, ("research_failed", "retry_research")),
        (
            {"research": "needs_more_info", "draft": None},
            ("research_needs_more_info", "retry_research"),
        ),
        ({"draft": None, "review": None}, ("researched", "run_draft")),
        ({"draft": "failed"}, ("draft_failed", "retry_draft")),
        ({"draft": "failed", "draft_attempts": 1}, ("draft_failed", "retry_draft")),
        ({"draft": "failed", "draft_attempts": 2}, ("draft_failed", "close")),
        ({"draft": "needs_more_info"}, ("draft_needs_more_info", "close")),
        ({"draft": "drafting", "review": None}, ("draft_drafting", "wait")),
        ({}, ("awaiting_review", "auto_review")),
        ({"review": "revise"}, ("revise_requested", "run_revise")),
        ({"review": "revise", "redrafts": 1}, ("revise_requested", "run_revise")),
        ({"review": "revise", "redrafts": 2}, ("revise_exhausted", "close")),
        ({"review": "revise", "redrafts": 3}, ("revise_exhausted", "close")),
        ({"review": "pending", "redrafts": 5}, ("awaiting_review", "auto_review")),
        ({"review": "rejected"}, ("rejected", "none")),
        ({"review": "approved"}, ("approved", "publish")),
        # The owner took it down: the agent leaves it down (an editor publish brings it back).
        ({"review": "approved", "published": "unpublished"}, ("unpublished", "none")),
        ({"review": "approved", "published": "published"}, ("published", "attach_images")),
        (
            {
                "review": "approved",
                "published": "published",
                "has_cover": True,
                "has_figure": False,
            },
            ("published", "attach_images"),
        ),
        (
            {"review": "approved", "published": "published", "has_cover": True, "has_figure": True},
            ("complete", "none"),
        ),
    ],
)
def test_each_state_has_one_next_action(
    overrides: dict[str, object], expected: tuple[str, str]
) -> None:
    assert state(**overrides) == expected


@pytest.mark.parametrize("status", ["failed", "needs_more_info"])
@pytest.mark.parametrize(
    ("attempts", "expected"),
    [(0, "retry_research"), (1, "retry_research"), (2, "close"), (3, "close")],
)
def test_research_closes_after_the_attempt_cap(status: str, attempts: int, expected: str) -> None:
    result = state(research=status, draft=None, research_attempts=attempts)
    assert result == (
        f"research_{status}" if expected == "retry_research" else "research_parked",
        expected,
    )


def test_attempts_do_not_affect_a_researched_card() -> None:
    assert state(draft=None, review=None, research_attempts=5) == ("researched", "run_draft")


# Every next_action the autopilot can execute without a person.
AUTONOMOUS_ACTIONS = {
    "run_research", "retry_research", "run_draft", "retry_draft", "auto_review",
    "run_revise", "publish", "attach_images", "close", "wait", "none",
}  # fmt: skip


def test_parked_research_closes() -> None:
    result = classify(
        research="failed", draft=None, review=None, published=None,
        has_cover=False, has_figure=False, research_attempts=MAX_RESEARCH_ATTEMPTS,
        max_redrafts=2,
    )  # fmt: skip
    assert (result.stage, result.next_action) == ("research_parked", "close")


def test_no_action_waits_on_a_person() -> None:
    research = [None, "researching", "researched", "needs_more_info", "failed"]
    draft = [None, "drafting", "drafted", "needs_more_info", "failed"]
    review = [None, "pending", "approved", "revise", "rejected"]
    published = [None, "published", "unpublished"]
    for r, d, rv, p, cover, attempts, d_attempts, redrafts in product(
        research, draft, review, published, [True, False],
        [0, MAX_RESEARCH_ATTEMPTS], [0, MAX_DRAFT_ATTEMPTS], [0, 2],
    ):  # fmt: skip
        action = classify(
            research=r, draft=d, review=rv, published=p,
            has_cover=cover, has_figure=cover, research_attempts=attempts,
            draft_attempts=d_attempts, redrafts=redrafts, max_redrafts=2,
        ).next_action  # fmt: skip
        assert action in AUTONOMOUS_ACTIONS, (r, d, rv, p, attempts, d_attempts, redrafts, action)


def test_used_and_failed_redrafts_both_count() -> None:
    log = [
        {"type": "review", "decision": "revise"},
        {"type": "redraft_failed", "error": "ProviderRejectedError: x"},
        {"type": "redraft", "note": "n"},
        {"type": "edit"},
    ]
    assert redrafts_used(log) == 2
    assert redrafts_used([]) == 0


def test_no_redraft_cap_closes_a_revise_at_once() -> None:
    assert state(review="revise", max_redrafts=0) == ("revise_exhausted", "close")


def test_close_reason_tag_is_known() -> None:
    from signalforge.core.reason_tags import REASON_TAGS

    assert CLOSE_REASON_TAG in REASON_TAGS


def test_accepted_cards_counts_redrafts_from_the_review_log() -> None:
    from datetime import UTC, datetime
    from types import SimpleNamespace
    from uuid import uuid4

    from signalforge.db.repositories.pipeline import PipelineRepository

    log = [{"type": "redraft"}, {"type": "redraft_failed"}]
    row = (uuid4(), "t", datetime.now(UTC), "accepted", "researched", 1, None,
           "drafted", 1, None, "revise", log, None, None, None)  # fmt: skip
    session = SimpleNamespace(execute=lambda _q: SimpleNamespace(all=lambda: [row]))
    repo = PipelineRepository(session)  # type: ignore[arg-type]
    [exhausted] = repo.accepted_cards(10, max_redrafts=2)
    assert (exhausted.stage, exhausted.next_action) == ("revise_exhausted", "close")
    [open_] = repo.accepted_cards(10, max_redrafts=3)
    assert (open_.stage, open_.next_action) == ("revise_requested", "run_revise")
