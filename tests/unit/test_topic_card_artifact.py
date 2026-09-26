from uuid import uuid4

import pytest
from pydantic import ValidationError

from signalforge.core.artifacts.topic_card import ArticleFormat, RiskFlag, TopicCard


def make(**overrides: object) -> TopicCard:
    fields: dict[str, object] = {
        "signal_id": uuid4(),
        "what_happened": "A thing happened.",
        "why_it_matters": "It matters.",
        "novelty": 0.7,
        "signal_strength": 0.6,
        "coverage_gap": "",
        "suggested_angle": "An angle.",
        "format": "explainer",
        "evergreen_score": 0.5,
        "confidence": 0.8,
        "risk_flags": ["hype"],
        "prompt_version": "card-v1",
        "model": "m",
    }
    return TopicCard(**{**fields, **overrides})  # type: ignore[arg-type]


def test_valid_card() -> None:
    card = make()
    assert card.format is ArticleFormat.EXPLAINER
    assert card.risk_flags == (RiskFlag.HYPE,)


@pytest.mark.parametrize(
    "overrides",
    [
        {"novelty": 1.1},
        {"confidence": -0.1},
        {"evergreen_score": 2},
        {"signal_strength": -1},
        {"format": "listicle"},
        {"what_happened": ""},
        {"what_happened": "x" * 401},
        {"why_it_matters": "x" * 301},
        {"coverage_gap": "x" * 301},
        {"suggested_angle": ""},
        {"risk_flags": ["spicy"]},
        {"extra": 1},
    ],
)
def test_invalid_rejected(overrides: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        make(**overrides)
