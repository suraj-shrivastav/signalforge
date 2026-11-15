import threading
from typing import Any

from apps.api import agent_runs


def test_last_result_is_written_before_the_slot_is_released(monkeypatch: Any) -> None:
    monkeypatch.setattr(agent_runs, "_STATE", {"running": None, "last": {}})
    real = agent_runs._LOCK
    seen: list[Any] = []

    class SpyLock:
        def acquire(self, blocking: bool = True) -> bool:
            return real.acquire(blocking)

        def release(self) -> None:
            # What a poll sees at the instant the slot frees up.
            seen.append((agent_runs.status()["running"], agent_runs.status()["last"].get("x")))
            real.release()

    monkeypatch.setattr(agent_runs, "_LOCK", SpyLock())
    done = threading.Event()

    def job() -> dict[str, int]:
        return {"n": 1}

    assert agent_runs.start_job("x", job)
    # Wait on the lock itself (no sleeps): it is free again only after the thread finished.
    while not real.acquire(blocking=False):
        done.wait(0.001)
    real.release()
    running, last = seen[0]
    assert running is None
    assert last == {**last, "ok": True, "result": {"n": 1}}


def test_the_slot_is_released_even_if_recording_the_result_fails(monkeypatch: Any) -> None:
    class BadLast(dict[str, Any]):
        def __setitem__(self, key: str, value: Any) -> None:
            raise RuntimeError("boom")

    monkeypatch.setattr(agent_runs, "_STATE", {"running": None, "last": BadLast()})
    assert agent_runs.start_job("x", lambda: {"n": 1})
    while not agent_runs._LOCK.acquire(blocking=False):
        threading.Event().wait(0.001)
    agent_runs._LOCK.release()
    assert agent_runs._STATE["running"] is None
