"""Rules ranker: a fixed weighted sum over the card's own signals plus assessment relevance."""

from signalforge.core.artifacts.topic_card import RiskFlag, TopicCard

# ponytail: weights are a first guess; tune from editor decision data after week one.
WEIGHTS: dict[str, float] = {
    "relevance": 0.35,
    "novelty": 0.30,
    "signal_strength": 0.20,
    "confidence": 0.15,
}
RISK_PENALTY = 0.1
_PENALISED = frozenset({RiskFlag.UNVERIFIED_CLAIM, RiskFlag.HYPE})


def _clip(value: float) -> float:
    return min(1.0, max(0.0, value))


def score(relevance: float, card: TopicCard) -> float:
    """Weighted sum of clipped inputs, minus 0.1 per penalised risk flag, within [0, 1]."""
    total = (
        WEIGHTS["relevance"] * _clip(relevance)
        + WEIGHTS["novelty"] * _clip(card.novelty)
        + WEIGHTS["signal_strength"] * _clip(card.signal_strength)
        + WEIGHTS["confidence"] * _clip(card.confidence)
    )
    penalty = RISK_PENALTY * len(_PENALISED.intersection(card.risk_flags))
    return _clip(total - penalty)


class RulesRanker:
    """Card-level ranker. Deviates from the PRD's cluster argument: cards are the unit here."""

    name = "rules"

    def score(self, relevance: float, card: TopicCard) -> float:
        return score(relevance, card)
