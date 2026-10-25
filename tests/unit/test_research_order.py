from types import SimpleNamespace
from typing import Any

from signalforge.db.repositories.research import ResearchRepository


def test_the_research_queue_takes_the_best_scoring_card_first() -> None:
    """Research is costly, so the highest scoring accepted card goes first, oldest on ties."""
    seen: list[Any] = []

    def execute(query: Any) -> SimpleNamespace:
        seen.append(query)
        return SimpleNamespace(all=lambda: [])

    ResearchRepository(SimpleNamespace(execute=execute)).list_accepted_unresearched(1)  # type: ignore[arg-type]
    order = str(seen[0].compile()).rsplit("ORDER BY", 1)[1].split("LIMIT")[0]
    columns = [part.strip() for part in order.split(",")]
    assert columns[0] == "topic_cards.score DESC"
    assert columns[1] == "topic_cards.created_at ASC"
