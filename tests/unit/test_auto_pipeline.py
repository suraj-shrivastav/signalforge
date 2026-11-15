from types import SimpleNamespace
from typing import Any

import pytest
from apps.api import auto_pipeline
from apps.worker import draft, research

from signalforge.core.config import Settings


class _Session:
    def __init__(self, used: int) -> None:
        self.used = used

    def __enter__(self) -> "_Session":
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def scalar(self, _query: object) -> int:
        return self.used


def _wire(
    monkeypatch: pytest.MonkeyPatch, used: int, paused: bool = False
) -> list[tuple[str, int]]:
    calls: list[tuple[str, int]] = []
    engine = SimpleNamespace(dispose=lambda: calls.append(("dispose", 0)))
    monkeypatch.setattr(auto_pipeline, "create_db_engine", lambda *_a: engine)
    monkeypatch.setattr(auto_pipeline, "create_session_factory", lambda _e: lambda: _Session(used))

    def fake_research(_engine: object, limit: int) -> SimpleNamespace:
        calls.append(("research", limit))
        return SimpleNamespace(researched=limit)

    def fake_draft(_engine: object, limit: int) -> SimpleNamespace:
        calls.append(("draft", limit))
        return SimpleNamespace(drafted=limit)

    row = SimpleNamespace(paused=paused, paused_until=None)
    monkeypatch.setattr(
        auto_pipeline, "ControlsRepository", lambda _s: SimpleNamespace(get=lambda: row)
    )
    monkeypatch.setattr(research, "run", fake_research)
    monkeypatch.setattr(draft, "run", fake_draft)
    return calls


def _settings(cap: int) -> Settings:
    return Settings(  # type: ignore[call-arg]
        _env_file=None,
        database_url="postgresql://u:p@localhost/db",  # type: ignore[arg-type]
        auto_pipeline_daily_cap=cap,
    )


def test_runs_research_then_draft_within_the_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _wire(monkeypatch, used=8)
    auto_pipeline.run_after_accept(_settings(10))
    assert calls == [("research", 1), ("draft", 1), ("dispose", 0)]


def test_skips_while_the_pipeline_is_paused(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _wire(monkeypatch, used=0, paused=True)
    auto_pipeline.run_after_accept(_settings(10))
    assert calls == [("dispose", 0)]  # no research, no draft


def test_skips_when_the_daily_cap_is_reached(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _wire(monkeypatch, used=10)
    auto_pipeline.run_after_accept(_settings(10))
    assert calls == [("dispose", 0)]


def test_a_failing_stage_never_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _wire(monkeypatch, used=0)

    def boom(*_a: Any) -> None:
        raise RuntimeError("down")

    monkeypatch.setattr(research, "run", boom)
    auto_pipeline.run_after_accept(_settings(10))
    assert calls == [("dispose", 0)]


def test_a_pass_waits_for_a_run_the_agent_started(monkeypatch: pytest.MonkeyPatch) -> None:
    """Research never runs in parallel with an agent run: both share one slot."""
    import threading

    from apps.api import agent_runs

    calls = _wire(monkeypatch, used=0)
    entered = threading.Event()
    done = threading.Event()

    def worker() -> None:
        entered.set()
        auto_pipeline.run_after_accept(_settings(10))
        done.set()

    with agent_runs.hold("tick"):
        assert agent_runs.start("research", _settings(10), 1, False) is False
        threading.Thread(target=worker, daemon=True).start()
        assert entered.wait(2)
        assert not done.wait(0.3)  # blocked behind the agent's run
        assert ("research", 1) not in calls
    assert done.wait(5)
    assert ("research", 1) in calls
