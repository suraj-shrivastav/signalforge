"""The research eval script's pure summary function."""

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest


def _load_script() -> ModuleType:
    path = Path(__file__).resolve().parents[2] / "scripts" / "eval_research.py"
    spec = importlib.util.spec_from_file_location("eval_research_script", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


summarize = _load_script().summarize


def _row(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "card_id": "c",
        "host": "arxiv.org",
        "documents": 4,
        "primary_full_text": True,
        "claims": 6,
        "numeric_claims": 2,
        "status": "researched",
        "failure_class": None,
        "cost_usd": 0.01,
        "calls": 6,
        "extraction_failures": 0,
    }
    row.update(overrides)
    return row


def test_summarize_three_rows() -> None:
    rows = [
        _row(),
        _row(
            host="example.com",
            documents=2,
            primary_full_text=False,
            claims=3,
            numeric_claims=0,
            cost_usd=0.02,
            calls=8,
            extraction_failures=1,
        ),
        _row(
            host="arxiv.org",
            documents=0,
            primary_full_text=False,
            claims=0,
            numeric_claims=0,
            status="needs_more_info",
            failure_class="blocked",
            cost_usd=0.0,
            calls=0,
        ),
    ]
    totals = summarize(rows)
    assert totals["cards"] == 3
    assert totals["researched_share"] == pytest.approx(2 / 3)
    assert totals["mean_claims"] == pytest.approx(3.0)
    assert totals["numeric_share_of_researched"] == pytest.approx(0.5)
    assert totals["full_text_share_arxiv"] == pytest.approx(0.5)
    assert totals["mean_cost_usd"] == pytest.approx(0.01)
    assert totals["mean_calls"] == pytest.approx(14 / 3)
    assert totals["extraction_success_rate"] == pytest.approx(5 / 6)
    assert totals["failure_classes"] == {"blocked": 1}


def test_summarize_empty_gives_zeros() -> None:
    totals = summarize([])
    assert totals["cards"] == 0
    for key in (
        "researched_share",
        "mean_claims",
        "numeric_share_of_researched",
        "full_text_share_arxiv",
        "mean_cost_usd",
        "mean_calls",
        "extraction_success_rate",
    ):
        assert totals[key] == 0
    assert totals["failure_classes"] == {}


def test_summarize_no_documents_attempted_has_zero_extraction_rate() -> None:
    totals = summarize([_row(documents=0, extraction_failures=0)])
    assert totals["extraction_success_rate"] == 0
