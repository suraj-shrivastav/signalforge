import logging
from types import SimpleNamespace
from typing import Any

import pytest
from apps.worker import assess as assess_mod
from apps.worker import tick

from signalforge.core.errors import SignalForgeError
from signalforge.plugins.sources import SOURCE_NAMES


class _Ctx:
    def __enter__(self) -> "_Ctx":
        return self

    def __exit__(self, *a: object) -> None:
        return None


def _setup(
    monkeypatch: pytest.MonkeyPatch,
    *,
    failing: set[str],
    provider: str = "openai",
    assess_raises: bool = False,
) -> dict[str, Any]:
    calls: dict[str, Any] = {"ingest": [], "assess": 0}
    monkeypatch.setattr(
        tick, "get_settings", lambda: SimpleNamespace(log_level="INFO", llm_provider=provider)
    )
    monkeypatch.setattr(tick, "configure_logging", lambda _l: None)
    monkeypatch.setattr(tick, "create_db_engine", lambda *_a: SimpleNamespace(dispose=lambda: None))
    monkeypatch.setattr(tick, "create_session_factory", lambda _e: lambda: _Ctx())
    monkeypatch.setattr(tick, "build_source", lambda name, _c: name)

    def fake_ingest(source: str, _s: object, *, since: object) -> SimpleNamespace:  # noqa: ARG001
        calls["ingest"].append(source)
        if source in failing:
            raise SignalForgeError("boom") if source != "bug" else RuntimeError("bug")
        return SimpleNamespace(fetched=3, inserted=2)

    def fake_assess(_e: object, limit: int) -> SimpleNamespace:
        calls["assess"] += 1
        calls["limit"] = limit
        if assess_raises:
            raise RuntimeError("llm down")
        return SimpleNamespace(considered=1, assessed=1, relevant=1, failed=0)

    monkeypatch.setattr(tick, "run_ingest", fake_ingest)
    monkeypatch.setattr(assess_mod, "run", fake_assess)
    return calls


def test_one_source_fails_others_run_and_assess_once(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    calls = _setup(monkeypatch, failing={SOURCE_NAMES[0]})
    with caplog.at_level(logging.ERROR):
        assert tick.main([]) == 0
    assert calls["ingest"] == list(SOURCE_NAMES)
    assert calls["assess"] == 1
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
        assert tick.main([]) == 0
    assert "assess failed" in caplog.text


def test_bad_args_rejected() -> None:
    for argv in (["--hours", "0"], ["--assess-limit", "501"]):
        with pytest.raises(SystemExit):
            tick.parse_args(argv)
