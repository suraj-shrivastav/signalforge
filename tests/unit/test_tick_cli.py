import logging
from types import SimpleNamespace
from typing import Any

import pytest
from apps.worker import assess as assess_mod
from apps.worker import cards as cards_mod
from apps.worker import draft as draft_mod
from apps.worker import research as research_mod
from apps.worker import tick

from signalforge.core.errors import SignalForgeError
from signalforge.plugins.sources import SOURCE_NAMES


class _Ctx:
    def __init__(self, stats: dict[str, Any]) -> None:
        self.stats = stats

    def __enter__(self) -> "_Ctx":
        self.stats["opened"] += 1
        return self

    def __exit__(self, *a: object) -> None:
        self.stats["closed"] += 1


def _setup(
    monkeypatch: pytest.MonkeyPatch,
    *,
    failing: set[str],
    provider: str = "openai",
    assess_raises: bool = False,
    cards_raises: bool = False,
    research_raises: bool = False,
    bugs: frozenset[str] = frozenset(),
) -> dict[str, Any]:
    calls: dict[str, Any] = {
        "ingest": [],
        "order": [],
        "assess": 0,
        "cards": 0,
        "opened": 0,
        "closed": 0,
        "disposed": 0,
    }
    monkeypatch.setattr(
        tick, "get_settings", lambda: SimpleNamespace(log_level="INFO", llm_provider=provider)
    )
    monkeypatch.setattr(tick, "configure_logging", lambda _l: None)
    monkeypatch.setattr(
        tick,
        "create_db_engine",
        lambda *_a: SimpleNamespace(
            dispose=lambda: calls.__setitem__("disposed", calls["disposed"] + 1)
        ),
    )
    monkeypatch.setattr(tick, "create_session_factory", lambda _e: lambda: _Ctx(calls))
    monkeypatch.setattr(tick, "build_source", lambda name, _c, **_kw: name)

    def fake_ingest(source: str, _s: object, *, since: object) -> SimpleNamespace:  # noqa: ARG001
        calls["ingest"].append(source)
        calls["order"].append("ingest")
        if source in failing:
            raise SignalForgeError("boom") if source not in bugs else RuntimeError("bug")
        return SimpleNamespace(fetched=3, inserted=2)

    def fake_assess(_e: object, limit: int) -> SimpleNamespace:
        calls["assess"] += 1
        calls["order"].append("assess")
        calls["limit"] = limit
        if assess_raises:
            raise RuntimeError("llm down")
        return SimpleNamespace(
            considered=1, assessed=1, relevant=1, failed=0, stopped_on_budget=False
        )

    def fake_cards(_e: object, limit: int) -> SimpleNamespace:
        calls["cards"] += 1
        calls["order"].append("cards")
        calls["cards_limit"] = limit
        if cards_raises:
            raise RuntimeError("cards down")
        return SimpleNamespace(considered=2, created=2, failed=0, stopped_on_budget=False)

    def fake_research(_e: object, limit: int) -> SimpleNamespace:
        calls["order"].append("research")
        calls["research_limit"] = limit
        if research_raises:
            raise RuntimeError("research down")
        return SimpleNamespace(considered=1, researched=1, needs_more_info=0, failed=0)

    def fake_draft(_e: object, limit: int) -> SimpleNamespace:
        calls["order"].append("draft")
        calls["draft_limit"] = limit
        return SimpleNamespace(considered=1, drafted=1, needs_more_info=0, failed=0)

    monkeypatch.setattr(cards_mod, "run", fake_cards)
    monkeypatch.setattr(tick, "run_ingest", fake_ingest)
    monkeypatch.setattr(assess_mod, "run", fake_assess)
    monkeypatch.setattr(research_mod, "run", fake_research)
    monkeypatch.setattr(draft_mod, "run", fake_draft)
    return calls


def test_one_source_fails_others_run_and_assess_once(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    capsys: pytest.CaptureFixture[str],
) -> None:
    calls = _setup(monkeypatch, failing={SOURCE_NAMES[0]})
    with caplog.at_level(logging.ERROR):
        assert tick.main([]) == 0
    assert calls["ingest"] == list(SOURCE_NAMES)
    assert calls["assess"] == 1
    assert calls["opened"] == calls["closed"] == len(SOURCE_NAMES)
    assert calls["disposed"] == 1
    out = capsys.readouterr().out
    assert f"{SOURCE_NAMES[0]}: FAILED (SignalForgeError)" in out
    assert f"{SOURCE_NAMES[1]}: fetched=3 inserted=2" in out
    assert "ingest failed" in caplog.text


def test_all_fail_exit_1_assess_still_attempted(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _setup(monkeypatch, failing=set(SOURCE_NAMES))
    assert tick.main(["--assess-limit", "5"]) == 1
    assert calls["assess"] == 1
    assert calls["limit"] == 5


def test_fake_provider_skips_assess(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _setup(monkeypatch, failing=set(), provider="fake")
    assert tick.main([]) == 0
    assert calls["assess"] == 0


def test_assess_failure_logged_exit_follows_ingest(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    _setup(monkeypatch, failing=set(), assess_raises=True)
    with caplog.at_level(logging.ERROR):
        assert tick.main([]) == 2
    assert "assess failed" in caplog.text


def test_bad_args_rejected() -> None:
    for argv in (
        ["--hours", "0"],
        ["--assess-limit", "501"],
        ["--cards-limit", "0"],
        ["--cards-limit", "201"],
        ["--research-limit", "51"],
        ["--draft-limit", "0"],
    ):
        with pytest.raises(SystemExit):
            tick.parse_args(argv)


def test_non_signalforge_error_counted_others_run_engine_disposed(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    first = SOURCE_NAMES[0]
    calls = _setup(monkeypatch, failing={first}, bugs=frozenset({first}))
    assert tick.main([]) == 0
    assert calls["ingest"] == list(SOURCE_NAMES)
    assert calls["disposed"] == 1
    assert f"{first}: FAILED (RuntimeError)" in capsys.readouterr().out


def test_all_fail_and_assess_fails_exit_1(monkeypatch: pytest.MonkeyPatch) -> None:
    _setup(monkeypatch, failing=set(SOURCE_NAMES), assess_raises=True)
    assert tick.main([]) == 1


def test_cards_run_after_assess_with_limit(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    calls = _setup(monkeypatch, failing=set())
    assert tick.main(["--cards-limit", "7"]) == 0
    assert calls["order"].index("cards") == calls["order"].index("assess") + 1
    assert calls["cards_limit"] == 7
    assert "cards: considered=2 created=2" in capsys.readouterr().out


def test_cards_default_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _setup(monkeypatch, failing=set())
    tick.main([])
    assert calls["cards_limit"] == 25


def test_cards_failure_exit_2_assess_kept(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    capsys: pytest.CaptureFixture[str],
) -> None:
    calls = _setup(monkeypatch, failing=set(), cards_raises=True)
    with caplog.at_level(logging.ERROR):
        assert tick.main([]) == 2
    out = capsys.readouterr().out
    assert "assess: considered=1" in out
    assert "cards: FAILED" in out
    assert "cards failed" in caplog.text
    assert calls["disposed"] == 1


def test_assess_failure_still_runs_cards(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _setup(monkeypatch, failing=set(), assess_raises=True)
    assert tick.main([]) == 2
    assert calls["cards"] == 1


def test_fake_provider_skips_cards_with_message(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    calls = _setup(monkeypatch, failing=set(), provider="fake")
    assert tick.main([]) == 0
    assert calls["cards"] == 0
    assert "cards: skipped (fake provider)" in capsys.readouterr().out


def test_research_then_draft_run_last_with_limits(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    calls = _setup(monkeypatch, failing=set())
    assert tick.main(["--research-limit", "3", "--draft-limit", "4"]) == 0
    assert calls["order"][-4:] == ["assess", "cards", "research", "draft"]
    assert (calls["research_limit"], calls["draft_limit"]) == (3, 4)
    out = capsys.readouterr().out
    assert "research: considered=1 researched=1" in out
    assert "draft: considered=1 drafted=1" in out


def test_research_failure_still_runs_draft_exit_2(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    calls = _setup(monkeypatch, failing=set(), research_raises=True)
    assert tick.main([]) == 2
    assert calls["order"][-1] == "draft"
    assert "research: FAILED" in capsys.readouterr().out


def test_fake_provider_skips_research_and_draft(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    calls = _setup(monkeypatch, failing=set(), provider="fake")
    assert tick.main([]) == 0
    assert "research" not in calls["order"]
    assert "draft" not in calls["order"]
    out = capsys.readouterr().out
    assert "research: skipped (fake provider)" in out
    assert "draft: skipped (fake provider)" in out
