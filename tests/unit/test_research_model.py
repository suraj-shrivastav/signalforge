from sqlalchemy import CheckConstraint, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB

from signalforge.db.base import Base
from signalforge.db.models import ResearchPackageRow

TABLE = Base.metadata.tables["research_packages"]


def test_model_maps_the_table() -> None:
    assert ResearchPackageRow.__table__ is TABLE


def test_one_package_per_card() -> None:
    uniques = [c for c in TABLE.constraints if isinstance(c, UniqueConstraint)]
    assert [(u.name, [col.name for col in u.columns]) for u in uniques] == [
        ("uq_research_packages_card_id", ["card_id"])
    ]


def test_status_check_constraint() -> None:
    checks = {c.name: str(c.sqltext) for c in TABLE.constraints if isinstance(c, CheckConstraint)}
    assert checks == {
        "ck_research_packages_status_allowed": (
            "status IN ('researching', 'researched', 'needs_more_info', 'failed')"
        )
    }


def test_card_fk_cascades() -> None:
    (fk,) = TABLE.c.card_id.foreign_keys
    assert fk.target_fullname == "topic_cards.id"
    assert fk.ondelete == "CASCADE"


def test_column_types() -> None:
    cols = TABLE.c
    assert isinstance(cols.status.type, String)
    assert cols.status.type.length == 32
    assert isinstance(cols.documents.type, JSONB)
    assert isinstance(cols.claims.type, JSONB)
    assert isinstance(cols.gaps_and_disagreements.type, Text)
    assert isinstance(cols.cost_usd.type, Numeric)
    assert (cols.cost_usd.type.precision, cols.cost_usd.type.scale) == (12, 6)
    assert isinstance(cols.calls.type, Integer)
    assert isinstance(cols.tokens.type, Integer)
    assert {c.name for c in cols if c.nullable} == {"failure_reason"}
