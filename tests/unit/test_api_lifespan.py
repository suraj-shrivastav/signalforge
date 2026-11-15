import pytest
from apps.api import main
from apps.api.main import create_app
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from signalforge.core.config import Settings
from signalforge.stale_runs import SweepResult

DSN = "postgresql://u:p@localhost:1/db"


def make() -> TestClient:
    return TestClient(create_app(Settings(_env_file=None, database_url=DSN)))  # type: ignore[call-arg,arg-type]


def test_startup_sweeps_stale_runs(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[object] = []

    def fake(_session: object, now: object) -> SweepResult:
        calls.append(now)
        return SweepResult(0, 0, 0)

    monkeypatch.setattr(main, "sweep_stale_runs", fake)
    with make() as client:
        assert client.get("/health").status_code == 200
    assert len(calls) == 1


def test_startup_survives_a_failing_sweep(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def boom(*_args: object) -> SweepResult:
        raise OperationalError("select 1", {}, Exception("db down"))

    monkeypatch.setattr(main, "sweep_stale_runs", boom)
    with make() as client:
        assert client.get("/health").status_code == 200
    assert "stale-run sweep failed" in capsys.readouterr().err
