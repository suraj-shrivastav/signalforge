"""Bounded retries with exponential backoff for external calls (standards §2)."""

import logging
import time
from collections.abc import Callable

from signalforge.core.errors import RateLimitedError, RetryableError

log = logging.getLogger(__name__)


def call_with_retry[T](
    fn: Callable[[], T],
    *,
    attempts: int = 3,
    base_delay: float = 0.5,
    sleep: Callable[[float], None] = time.sleep,
) -> T:
    """Call ``fn``, retrying only :class:`RetryableError` up to ``attempts`` times.

    A provider's ``Retry-After`` wins over the computed backoff. ``sleep`` is
    injectable so tests never wait.
    """
    if attempts < 1:
        raise ValueError("attempts must be at least 1")
    for attempt in range(1, attempts):
        try:
            return fn()
        except RetryableError as exc:
            delay = base_delay * 2 ** (attempt - 1)
            if isinstance(exc, RateLimitedError) and exc.retry_after_seconds is not None:
                delay = exc.retry_after_seconds
            log.warning(
                "retrying after error",
                extra={"attempt": attempt, "delay_s": delay, "error": str(exc)},
            )
            sleep(delay)
    return fn()
