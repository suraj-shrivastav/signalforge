"""Typed error hierarchy, split into retryable and permanent failures.

The pipeline engine reads :attr:`SignalForgeError.retryable` to decide whether a
failed job is re-queued with backoff or sent straight to a visible ``failed``
business state. Raising a bare :class:`Exception` anywhere in the pipeline is a
bug: it is neither classifiable nor loggable with context.
"""

from typing import ClassVar, Self


class SignalForgeError(Exception):
    """Base for every SignalForge error. Subclass it; never raise it directly."""

    retryable: ClassVar[bool] = False

    def __init__(self, message: str, *, context: dict[str, object] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.context: dict[str, object] = dict(context or {})

    def with_context(self, **fields: object) -> Self:
        """Attach diagnostic fields while re-raising. Never include secrets."""
        self.context.update(fields)
        return self

    def __str__(self) -> str:
        if not self.context:
            return self.message
        rendered = ", ".join(f"{key}={value!r}" for key, value in sorted(self.context.items()))
        return f"{self.message} ({rendered})"


class RetryableError(SignalForgeError):
    """Transient failure. Retrying the same call with backoff may succeed."""

    retryable: ClassVar[bool] = True


class PermanentError(SignalForgeError):
    """Deterministic failure. Retrying the same call cannot succeed."""

    retryable: ClassVar[bool] = False


class ProviderUnavailableError(RetryableError):
    """An external provider was unreachable or returned a server-side failure."""


class ProviderRejectedError(PermanentError):
    """An external provider rejected the request itself (4xx other than rate limiting)."""


class RateLimitedError(RetryableError):
    """A provider rejected the call for rate limiting."""

    def __init__(
        self,
        message: str,
        *,
        retry_after_seconds: float | None = None,
        context: dict[str, object] | None = None,
    ) -> None:
        super().__init__(message, context=context)
        self.retry_after_seconds = retry_after_seconds


class OperationTimeoutError(RetryableError):
    """An external call exceeded its timeout. Named to avoid shadowing ``TimeoutError``."""


class ConfigurationError(PermanentError):
    """Configuration is missing, malformed, or violates a startup invariant."""


class EditorKeyNotConfiguredError(ConfigurationError):
    """The editor write key is unset, so decision writes are refused."""


class ArtifactValidationError(PermanentError):
    """A payload failed validation at a boundary (API, LLM output, plugin output, config)."""


class BudgetExceededError(PermanentError):
    """A token, cost, or search budget was exhausted. Stop rather than overspend."""


class UnsupportedCapabilityError(PermanentError):
    """A model or provider lacks a capability the caller requires (JSON mode, tools, context)."""


def is_retryable(error: BaseException) -> bool:
    """Return whether ``error`` should be retried. Unknown errors are never retried."""
    return isinstance(error, SignalForgeError) and error.retryable
