"""The retryable/permanent split is a critical path: it decides job retry behaviour."""

import pytest

from signalforge.core.errors import (
    ArtifactValidationError,
    BudgetExceededError,
    ConfigurationError,
    OperationTimeoutError,
    PermanentError,
    ProviderUnavailableError,
    RateLimitedError,
    RetryableError,
    SignalForgeError,
    UnsupportedCapabilityError,
    is_retryable,
)

RETRYABLE = [ProviderUnavailableError, RateLimitedError, OperationTimeoutError]
PERMANENT = [
    ConfigurationError,
    ArtifactValidationError,
    BudgetExceededError,
    UnsupportedCapabilityError,
]


@pytest.mark.parametrize("error_type", RETRYABLE)
def test_retryable_errors_are_retryable(error_type: type[RetryableError]) -> None:
    assert is_retryable(error_type("boom")) is True


@pytest.mark.parametrize("error_type", PERMANENT)
def test_permanent_errors_are_not_retryable(error_type: type[PermanentError]) -> None:
    assert is_retryable(error_type("boom")) is False


def test_unknown_errors_are_never_retried() -> None:
    assert is_retryable(RuntimeError("boom")) is False


def test_every_error_derives_from_the_base() -> None:
    for error_type in (*RETRYABLE, *PERMANENT):
        assert issubclass(error_type, SignalForgeError)


def test_context_is_rendered_but_message_is_preserved() -> None:
    error = ProviderUnavailableError("gateway down", context={"provider": "openrouter"})
    error.with_context(status=503)

    assert error.message == "gateway down"
    assert str(error) == "gateway down (provider='openrouter', status=503)"


def test_context_defaults_to_empty_and_is_not_shared() -> None:
    first = ConfigurationError("missing key")
    second = ConfigurationError("missing key")
    first.with_context(field="api_key")

    assert str(second) == "missing key"


def test_rate_limit_carries_retry_after() -> None:
    error = RateLimitedError("slow down", retry_after_seconds=2.5)

    assert error.retry_after_seconds == 2.5
    assert is_retryable(error) is True
