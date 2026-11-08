from decimal import Decimal
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

from sqlalchemy.dialects import postgresql

from signalforge.core.artifacts.research import ResearchPackage, ResearchStatus
from signalforge.db.models.research import ResearchPackageRow
from signalforge.db.repositories.research import ResearchRepository
from signalforge.pipeline_state import MAX_RESEARCH_ATTEMPTS


def test_the_cap_is_two() -> None:
    assert MAX_RESEARCH_ATTEMPTS == 2


def test_attempts_column_defaults_to_zero_and_is_not_null() -> None:
    column = ResearchPackageRow.__table__.c.attempts
    assert not column.nullable
    assert column.default.arg == 0
    assert str(column.server_default.arg) == "0"


def test_insert_counts_each_attempt() -> None:
    seen: list[Any] = []

    def execute(statement: Any) -> SimpleNamespace:
        seen.append(statement)
        return SimpleNamespace(first=lambda: (1,))

    package = ResearchPackage(card_id=uuid4(), status=ResearchStatus.FAILED)
    ResearchRepository(SimpleNamespace(execute=execute)).insert(  # type: ignore[arg-type]
        package, cost_usd=Decimal("0"), calls=0, tokens=0
    )
    compiled = seen[0].compile(dialect=postgresql.dialect())  # type: ignore[no-untyped-call]
    sql = str(compiled)
    assert "attempts = (research_packages.attempts + " in sql
    assert 1 in compiled.params.values()  # first insert stores attempts = 1
    assert "research_packages.status IN" in sql  # researched rows are still never replaced
