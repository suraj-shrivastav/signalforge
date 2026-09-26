import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any

import pytest

from signalforge.core.artifacts.topic_card import ArticleFormat, RiskFlag, TopicCard
from signalforge.core.errors import ArtifactValidationError
from signalforge.db.repositories.cards import QueueItem, select_queue
from signalforge.plugins.rankers.rules import WEIGHTS, RulesRanker, score


def make(v: float, flags: tuple[RiskFlag, ...] = ()) -> TopicCard:
    return TopicCard(
        signal_id=uuid.uuid4(),
        what_happened="w",
        why_it_matters="m",
        novelty=v,
        signal_strength=v,
        coverage_gap="",
        suggested_angle="a",
        format=ArticleFormat.EXPLAINER,
        evergreen_score=v,
        confidence=v,
        risk_flags=flags,
        prompt_version="v",
        model="m",
    )


def test_weights_sum_to_one() -> None:
    assert sum(WEIGHTS.values()) == pytest.approx(1.0)


def test_extremes() -> None:
    assert score(1.0, make(1.0)) == pytest.approx(1.0)
    assert score(0.0, make(0.0)) == 0.0


def test_out_of_range_relevance_is_clipped() -> None:
    assert score(5.0, make(1.0)) == pytest.approx(1.0)
    assert score(-5.0, make(0.0)) == 0.0


def test_each_flag_lowers_by_point_one_and_floors() -> None:
    base = score(1.0, make(0.5))
    assert score(1.0, make(0.5, (RiskFlag.HYPE,))) == pytest.approx(base - 0.1)
    both = (RiskFlag.HYPE, RiskFlag.UNVERIFIED_CLAIM)
    assert score(1.0, make(0.5, both)) == pytest.approx(base - 0.2)
    assert score(0.0, make(0.0, both)) == 0.0
    assert score(1.0, make(0.5, (RiskFlag.STALE,))) == pytest.approx(base)


def test_ranker_delegates() -> None:
    assert RulesRanker.name == "rules"
    assert RulesRanker().score(0.5, make(0.5)) == score(0.5, make(0.5))


T0 = datetime(2026, 9, 1, tzinfo=UTC)


def item(n: int, s: float, novelty: float, at: int = 0) -> QueueItem:
    row: Any = SimpleNamespace(
        id=uuid.UUID(int=n), score=s, novelty=novelty, created_at=T0 + timedelta(minutes=at)
    )
    return QueueItem(row, "t", "s", "u", False, "proposed")


def test_select_queue_top_and_wildcards() -> None:
    items = [item(n, n / 20, 1.0 if n == 0 else (0.9 if n == 1 else 0.1)) for n in range(1, 21)]
    items[0] = item(1, 0.05, 0.9)
    items.append(item(99, 0.0, 1.0))
    out = select_queue(items, 15, 2)
    ids = [i.card.id.int for i in out]
    assert len(out) == 15
    assert len(set(ids)) == 15
    assert ids[:13] == list(range(20, 7, -1))
    assert [i.wildcard for i in out] == [False] * 13 + [True] * 2
    assert ids[13:] == [99, 1]


def test_select_queue_fewer_than_limit_and_ties() -> None:
    items = [item(2, 0.5, 0.5, 1), item(1, 0.5, 0.5, 1), item(3, 0.5, 0.5, 5)]
    out = select_queue(items, 15, 2)
    assert [i.card.id.int for i in out[:1]] == [3]
    assert len({i.card.id for i in out}) == 3
    assert select_queue([], 15, 2) == []


@pytest.mark.parametrize(("limit", "slots"), [(0, 0), (5, 6), (5, -1)])
def test_select_queue_validates(limit: int, slots: int) -> None:
    with pytest.raises(ArtifactValidationError):
        select_queue([], limit, slots)
