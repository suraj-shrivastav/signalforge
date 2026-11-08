"""Failure classes prefix every research failure reason."""

import uuid
from types import SimpleNamespace
from typing import Any

from signalforge.core.errors import BudgetExceededError, ProviderRejectedError
from signalforge.stages.research import _process_card
from signalforge.stages.research_failure import FailureClass, reason


def test_reason_prefixes_the_class() -> None:
    assert reason(FailureClass.BLOCKED, "403 from host") == "blocked: 403 from host"
    assert {c.value for c in FailureClass} == {
        "blocked",
        "empty",
        "no_claims",
        "thin",
        "budget",
        "error",
    }


def test_reason_is_cut_to_500_characters() -> None:
    out = reason(FailureClass.ERROR, "x" * 1000)
    assert len(out) == 500
    assert out.startswith("error: ")


class _Fetcher:
    def __init__(self, html: str | Exception) -> None:
        self.html = html

    def fetch_html(self, url: str) -> str:  # noqa: ARG002
        if isinstance(self.html, Exception):
            raise self.html
        return self.html


class _Search:
    def search(self, query: str, max_results: int = 5) -> list[Any]:  # noqa: ARG002
        return []


class _Gateway:
    def __init__(self, exc: Exception | None = None) -> None:
        self.exc = exc

    def complete_json(self, **kwargs: Any) -> Any:
        if self.exc is not None:
            raise self.exc
        return kwargs["schema"](claims=[])

    def embed(self, **kwargs: Any) -> Any:  # noqa: ARG002
        raise AssertionError("not reached")


_PAGE = "<html><body><article>" + "<p>The model scores 91 percent on the test set.</p>" * 40
_PAGE += "</article></body></html>"


def _run(fetcher: _Fetcher, gateway: _Gateway | None = None) -> tuple[Any, str | None]:
    card = SimpleNamespace(id=uuid.uuid4(), what_happened="what", why_it_matters="why")
    signal = SimpleNamespace(canonical_url="https://example.com/x", title="t", source="rss")
    return _process_card(
        gateway,  # type: ignore[arg-type]
        fetcher,
        _Search(),
        card,  # type: ignore[arg-type]
        signal,  # type: ignore[arg-type]
        uuid.uuid4(),
    )


def test_fetch_error_is_blocked() -> None:
    _, why = _run(_Fetcher(ProviderRejectedError("no", context={"status": 403})))
    assert why is not None
    assert why.startswith("blocked: ")


def test_empty_primary_text_is_empty() -> None:
    _, why = _run(_Fetcher("<html><body></body></html>"))
    assert why is not None
    assert why.startswith("empty: ")


def test_zero_claims_is_no_claims() -> None:
    _, why = _run(_Fetcher(_PAGE), _Gateway())
    assert why is not None
    assert why.startswith("no_claims: ")


def test_budget_error_is_budget() -> None:
    _, why = _run(_Fetcher(_PAGE), _Gateway(BudgetExceededError("over")))
    assert why is not None
    assert why.startswith("budget: ")
