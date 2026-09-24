"""Structured JSON logging with a correlation ID on every record.

Configured once, at a process entry point, with :func:`configure_logging`.
Library code only calls ``logging.getLogger(__name__)``. The correlation ID is
the PRD section 40 identifier (``request_id`` for an LLM call, ``stage_run_id``
for a stage run), so a log line joins to its ``llm_calls`` or ``stage_runs`` row.
"""

import json
import logging
import re
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

REDACTED = "***"

_correlation_id: ContextVar[str | None] = ContextVar("correlation_id", default=None)

# Field names whose values are never logged, and credentials embedded in a URL.
_SECRET_KEY = re.compile(r"password|secret|token|api_?key|authorization|credential", re.I)
_URL_CREDENTIALS = re.compile(r"(?<=://)([^/\s:@]+):([^/\s@]+)@")

# Attributes every LogRecord has. Anything else came from ``extra=`` and is logged.
_STANDARD_ATTRS = frozenset(vars(logging.makeLogRecord({}))) | {"message", "asctime", "taskName"}


@contextmanager
def correlation_id(value: str) -> Iterator[None]:
    """Attach ``value`` to every record logged inside the block, in this task or thread."""
    token = _correlation_id.set(value)
    try:
        yield
    finally:
        _correlation_id.reset(token)


def current_correlation_id() -> str | None:
    return _correlation_id.get()


def redact_text(text: str) -> str:
    return _URL_CREDENTIALS.sub(rf"\1:{REDACTED}@", text)


def _redact(key: str, value: Any) -> Any:
    if _SECRET_KEY.search(key):
        return REDACTED
    if isinstance(value, str):
        return redact_text(value)
    return value


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": redact_text(record.getMessage()),
            "correlation_id": _correlation_id.get(),
        }
        for key, value in vars(record).items():
            if key not in _STANDARD_ATTRS:
                payload[key] = _redact(key, value)
        if record.exc_info:
            payload["exception"] = redact_text(self.formatException(record.exc_info))
        # default=str keeps Decimal exact; a float would drift cost figures.
        return json.dumps(payload, default=str)


def configure_logging(level: str = "INFO") -> None:
    """Route the root logger to stderr as JSON. Idempotent; call once per process."""
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level.upper())


def log_llm_call(
    logger: logging.Logger,
    *,
    request_id: str,
    stage_run_id: str,
    role: str,
    provider: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
    cost_usd: Decimal,
    latency_ms: int,
    success: bool,
) -> None:
    """The one line every LLM call must produce (standards section 6, PRD section 40)."""
    logger.log(
        logging.INFO if success else logging.WARNING,
        "llm_call",
        extra={
            "request_id": request_id,
            "stage_run_id": stage_run_id,
            "role": role,
            "provider": provider,
            "model": model,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cost_usd": cost_usd,
            "latency_ms": latency_ms,
            "success": success,
        },
    )
