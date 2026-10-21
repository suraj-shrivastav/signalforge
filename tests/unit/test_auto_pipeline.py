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


def _wire(monkeypatch: pytest.MonkeyPatch, used: int) -> list[tuple[str, int]]:
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
    assert calls == [("research", 2), ("draft", 3), ("dispose", 0)]


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
