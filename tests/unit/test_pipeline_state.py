import pytest

from signalforge.pipeline_state import classify


def state(**kw: object) -> tuple[str, str]:
    base: dict[str, object] = {
        "research": "researched", "draft": "drafted", "review": "pending",
        "published": None, "has_cover": False, "has_figure": False,
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
        ({"draft": "needs_more_info"}, ("draft_needs_more_info", "human_review")),
        ({}, ("awaiting_review", "auto_review")),
        ({"review": "revise"}, ("revise_requested", "run_revise")),
        ({"review": "rejected"}, ("rejected", "none")),
        ({"review": "approved"}, ("approved", "publish")),
        ({"review": "approved", "published": "unpublished"}, ("approved", "publish")),
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
    [(0, "retry_research"), (1, "retry_research"), (2, "parked"), (3, "parked")],
)
def test_research_is_parked_after_the_attempt_cap(
    status: str, attempts: int, expected: str
) -> None:
    result = state(research=status, draft=None, research_attempts=attempts)
    assert result == (
        f"research_{status}" if expected == "retry_research" else "research_parked",
        expected,
    )


def test_attempts_do_not_affect_a_researched_card() -> None:
    assert state(draft=None, review=None, research_attempts=5) == ("researched", "run_draft")
