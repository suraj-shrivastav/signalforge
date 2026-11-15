from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from signalforge.control_policy import is_paused, slot_id

NOW = datetime(2026, 11, 15, 7, 30, tzinfo=UTC)


def row(**kw: object) -> SimpleNamespace:
    return SimpleNamespace(**{"paused": False, "paused_until": None, **kw})


def test_not_paused() -> None:
    assert not is_paused(row(), NOW)


def test_manual_pause_has_no_expiry() -> None:
    assert is_paused(row(paused=True), NOW)


def test_breaker_pause_expires() -> None:
    assert is_paused(row(paused=True, paused_until=NOW + timedelta(minutes=1)), NOW)
    assert not is_paused(row(paused=True, paused_until=NOW - timedelta(minutes=1)), NOW)


def test_slot_id_rounds_down_to_six_hours() -> None:
    assert slot_id(datetime(2026, 11, 15, 0, 0)) == "2026-11-15-00"
    assert slot_id(datetime(2026, 11, 15, 5, 59)) == "2026-11-15-00"
    assert slot_id(datetime(2026, 11, 15, 6, 0)) == "2026-11-15-06"
    assert slot_id(datetime(2026, 11, 15, 23, 59)) == "2026-11-15-18"
