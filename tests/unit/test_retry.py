import pytest

from signalforge.core.errors import (
    PermanentError,
    ProviderRejectedError,
    ProviderUnavailableError,
    RateLimitedError,
    is_retryable,
)
from signalforge.core.retry import call_with_retry


class Flaky:
    def __init__(self, failures: list[Exception], result: str = "ok") -> None:
        self.failures = failures
        self.result = result
        self.calls = 0

    def __call__(self) -> str:
        self.calls += 1
        if self.failures:
            raise self.failures.pop(0)
        return self.result


def test_retries_retryable_errors_with_exponential_backoff() -> None:
    delays: list[float] = []
    fn = Flaky([ProviderUnavailableError("a"), ProviderUnavailableError("b")])
    assert call_with_retry(fn, attempts=3, base_delay=1.0, sleep=delays.append) == "ok"
    assert fn.calls == 3
    assert delays == [1.0, 2.0]


def test_gives_up_after_the_last_attempt() -> None:
    fn = Flaky([ProviderUnavailableError("a")] * 3)
    with pytest.raises(ProviderUnavailableError):
        call_with_retry(fn, attempts=3, sleep=lambda _: None)
    assert fn.calls == 3


def test_permanent_errors_are_not_retried() -> None:
    fn = Flaky([ProviderRejectedError("nope")])
    with pytest.raises(ProviderRejectedError):
        call_with_retry(fn, sleep=lambda _: None)
    assert fn.calls == 1


def test_retry_after_overrides_backoff() -> None:
    delays: list[float] = []
    fn = Flaky([RateLimitedError("slow down", retry_after_seconds=7.0)])
    call_with_retry(fn, base_delay=0.1, sleep=delays.append)
    assert delays == [7.0]


def test_attempts_must_be_positive() -> None:
    with pytest.raises(ValueError, match="attempts"):
        call_with_retry(lambda: 1, attempts=0)


def test_provider_rejected_is_permanent() -> None:
    assert issubclass(ProviderRejectedError, PermanentError)
    assert not is_retryable(ProviderRejectedError("x"))
