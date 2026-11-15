from decimal import Decimal
from types import SimpleNamespace
from typing import Any

import pytest

from signalforge.core.budget import BudgetLimits
from signalforge.stages import draft as draft_stage


class FakeRepo:
    def __init__(self, _session: Any, existing: Any) -> None:
        self.existing = existing
        self.failed: list[tuple[Any, str | None]] = []

    def list_revisions(self, _limit: int) -> list[Any]:
        card = SimpleNamespace(id="c", suggested_angle="angle")
        signal = SimpleNamespace(source_type="x", canonical_url="u")
        return [(card, signal, SimpleNamespace(), self.existing)]

    def record_failed_revision(self, row: Any, reason: str | None) -> None:
        self.failed.append((row, reason))


def test_an_untyped_redraft_error_is_recorded_so_the_cap_counts_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    existing = SimpleNamespace(review_note="tighten the lead")
    repos: list[FakeRepo] = []

    def make_repo(session: Any) -> FakeRepo:
        repos.append(FakeRepo(session, existing))
        return repos[0]

    def boom(*_a: Any, **_k: Any) -> None:
        raise RuntimeError("token sk-secret leaked in message")

    commits: list[int] = []
    session = SimpleNamespace(
        add=lambda _o: None,
        commit=lambda: commits.append(len(repos[0].failed) if repos else 0),
        rollback=lambda: None,
        get=lambda *_a: None,
    )
    monkeypatch.setattr(draft_stage, "ArticleDraftRepository", make_repo)
    monkeypatch.setattr(draft_stage, "_check_families", lambda _g: None)
    monkeypatch.setattr(draft_stage, "_template_for", lambda *_a: None)
    monkeypatch.setattr(draft_stage, "_package", lambda _r: None)
    monkeypatch.setattr(draft_stage, "_process_card", boom)
    monkeypatch.setattr(draft_stage, "StageRun", lambda **kw: SimpleNamespace(id="r", **kw))

    with pytest.raises(RuntimeError):
        draft_stage.run_draft(
            session,  # type: ignore[arg-type]
            lambda _s, _b: None,  # type: ignore[arg-type,return-value]
            budget_limits=BudgetLimits(max_cost_usd=Decimal("1")),
            revise=True,
        )
    assert [(r, reason) for r, reason in repos[0].failed] == [(existing, "RuntimeError")]
    assert commits[-1] == 1  # committed before the run-level rollback, so the event survives
