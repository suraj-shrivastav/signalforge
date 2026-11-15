from decimal import Decimal
from typing import Any

from signalforge.core.config import Settings
from signalforge.llm.roles import build_roles, unpriced_models

DSN = "postgresql://u:p@localhost:5432/db"


def build(**overrides: Any) -> Settings:
    values: dict[str, Any] = {"database_url": DSN, **overrides}
    return Settings(_env_file=None, **values)  # type: ignore[call-arg]


def test_prices_flow_into_role_specs() -> None:
    s = build(
        llm_model_claim_judge="google/j",
        llm_prices={"google/j": {"input": "1", "output": "2"}},
    )
    spec = build_roles(s)["claim_judge"]
    assert (spec.input_usd_per_mtok, spec.output_usd_per_mtok) == (Decimal("1"), Decimal("2"))
    assert "google/j" not in unpriced_models(build_roles(s))
    assert s.llm_model_article_writer in unpriced_models(build_roles(s))
