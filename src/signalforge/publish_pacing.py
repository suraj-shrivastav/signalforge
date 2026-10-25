"""When the next article may go out: a minimum gap between publishes and a daily cap.

Pure functions. Drafts that pass review wait approved until a slot opens, so articles reach
the site spread over the day instead of all at once.
"""

from collections.abc import Sequence
from datetime import datetime, timedelta

_DAY = timedelta(days=1)


def next_publish_time(
    published: Sequence[datetime], now: datetime, *, min_gap: timedelta, daily_cap: int
) -> datetime:
    """Earliest time at or after ``now`` when one more article may publish.

    ``published`` holds the publish times of the last 24 hours (older ones do not matter).
    A slot needs ``min_gap`` since the latest publish and fewer than ``daily_cap`` publishes
    in the 24 hours before it.
    """
    times = sorted(published)
    at = now
    if times:
        at = max(at, times[-1] + min_gap)
    recent = [t for t in times if t > at - _DAY]
    if len(recent) >= daily_cap:
        at = max(at, recent[len(recent) - daily_cap] + _DAY)
    return at
