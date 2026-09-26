from uuid import uuid4

import pytest
from pydantic import ValidationError

from signalforge.core.artifacts.assessment import Category, SignalAssessment


def make(**overrides: object) -> SignalAssessment:
    fields: dict[str, object] = {
        "signal_id": uuid4(),
        "is_relevant": True,
        "relevance_score": 0.8,
        "category": "tool",
        "summary": "A summary.",
        "why_it_matters": "It matters.",
        "prompt_version": "assess-v1",
        "model": "m",
    }
    return SignalAssessment(**{**fields, **overrides})  # type: ignore[arg-type]


def test_valid_assessment() -> None:
    assert make().category is Category.TOOL


@pytest.mark.parametrize(
    "overrides",
    [
        {"relevance_score": -0.1},
        {"relevance_score": 1.1},
        {"summary": ""},
        {"summary": "x" * 301},
        {"why_it_matters": ""},
        {"why_it_matters": "x" * 301},
        {"category": "gossip"},
        {"extra": 1},
    ],
)
def test_invalid_rejected(overrides: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        make(**overrides)
