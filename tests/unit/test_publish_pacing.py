from datetime import UTC, datetime, timedelta

from signalforge.publish_pacing import next_publish_time

NOW = datetime(2026, 10, 25, 12, 0, tzinfo=UTC)
GAP = timedelta(hours=4)


def at(hours_ago: float) -> datetime:
    return NOW - timedelta(hours=hours_ago)


def slot(published: list[datetime], cap: int = 3) -> datetime:
    return next_publish_time(published, NOW, min_gap=GAP, daily_cap=cap)


def test_nothing_published_yet_means_now() -> None:
    assert slot([]) == NOW


def test_a_recent_publish_delays_the_next_by_the_gap() -> None:
    assert slot([at(1)]) == at(1) + GAP


def test_an_old_enough_publish_allows_now() -> None:
    assert slot([at(5)]) == NOW


def test_the_daily_cap_waits_for_the_oldest_publish_to_age_out() -> None:
    published = [at(23), at(18), at(10)]  # three in the last day, last one 10 hours ago
    assert slot(published, cap=3) == at(23) + timedelta(days=1)


def test_under_the_cap_only_the_gap_applies() -> None:
    assert slot([at(23), at(10)], cap=3) == NOW


def test_the_gap_can_push_the_slot_past_publishes_that_age_out() -> None:
    # at(23) and at(22) leave the 24 hour window by the time the gap after at(1) is over
    assert slot([at(23), at(22), at(1)], cap=3) == at(1) + GAP


def test_unsorted_input_gives_the_same_answer() -> None:
    assert slot([at(1), at(23), at(10)]) == slot([at(23), at(10), at(1)])
