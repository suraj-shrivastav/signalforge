import pytest
from apps.worker.triage_metrics import compute_metrics, format_metrics, parse_args, percentile

DECISIONS = [
    ("accepted", ["timely"], 1000),
    ("accepted", [], 3000),
    ("rejected", ["stale", "timely"], 2000),
    ("snoozed", [], 4000),
]


def test_rates_and_percentiles() -> None:
    m = compute_metrics(6, DECISIONS, 2)
    assert m.cards_created == 6
    assert m.decided == 4
    assert m.accept_rate == 0.5
    assert m.snooze_rate == 0.25
    assert m.median_ms == 2500
    assert m.p90_ms == 4000
    assert m.waiting == 2
    assert m.reason_tags == {"stale": 1, "timely": 2}


def test_nulls_ignored() -> None:
    m = compute_metrics(2, [("accepted", [], None), ("rejected", [], 500)], 0)
    assert m.median_ms == 500
    assert m.p90_ms == 500


def test_all_null_ms_is_na() -> None:
    m = compute_metrics(1, [("accepted", [], None)], 0)
    assert m.median_ms is None
    assert "median_ms=n/a" in format_metrics(m)


def test_no_decisions_na_without_exception() -> None:
    m = compute_metrics(3, [], 3)
    assert m.accept_rate is None
    assert m.snooze_rate is None
    out = format_metrics(m)
    assert "accept_rate=n/a" in out
    assert "median_ms=n/a" in out
    assert "reason_tags: none" in out
    assert "waiting=3" in out


def test_format_accept_rate() -> None:
    assert "accept_rate=0.50" in format_metrics(compute_metrics(4, DECISIONS, 0))


def test_percentile_nearest_rank() -> None:
    assert percentile([], 90) is None
    assert percentile(list(range(1, 11)), 90) == 9


def test_days_bounds() -> None:
    assert parse_args([]).days == 14
    for bad in ("0", "91"):
        with pytest.raises(SystemExit):
            parse_args(["--days", bad])
