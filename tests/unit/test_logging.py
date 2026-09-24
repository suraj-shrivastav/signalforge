"""Logging must carry the correlation ID and must never emit a secret."""

import json
import logging
from decimal import Decimal

import pytest

from signalforge.core.logging import (
    REDACTED,
    JsonFormatter,
    configure_logging,
    correlation_id,
    log_llm_call,
)


def _emit(caplog: pytest.LogCaptureFixture) -> dict[str, object]:
    record = caplog.records[-1]
    parsed: dict[str, object] = json.loads(JsonFormatter().format(record))
    return parsed


def test_record_carries_correlation_id_only_inside_the_block(
    caplog: pytest.LogCaptureFixture,
) -> None:
    log = logging.getLogger("t")
    with caplog.at_level(logging.INFO):
        with correlation_id("run-1"):
            log.info("inside")
            # Formatted inside the block, as a real handler does at emit time.
            assert _emit(caplog)["correlation_id"] == "run-1"
        log.info("outside")
        assert _emit(caplog)["correlation_id"] is None


def test_secret_fields_and_url_passwords_are_masked(caplog: pytest.LogCaptureFixture) -> None:
    log = logging.getLogger("t")
    with caplog.at_level(logging.INFO):
        log.info(
            "connect postgresql://user:hunter2@host:5432/db",
            extra={"api_key": "sk-123", "dsn": "postgresql://u:pw9@h/db", "topic": "ok"},
        )
    out = _emit(caplog)
    dumped = json.dumps(out)
    for leaked in ("hunter2", "sk-123", "pw9"):
        assert leaked not in dumped
    assert out["api_key"] == REDACTED
    assert out["topic"] == "ok"


def test_llm_call_line_has_the_prd_fields_with_exact_cost(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO):
        log_llm_call(
            logging.getLogger("llm"),
            request_id="r1",
            stage_run_id="s1",
            role="extract",
            provider="fake",
            model="m",
            input_tokens=10,
            output_tokens=5,
            cost_usd=Decimal("0.0100"),
            latency_ms=42,
            success=True,
        )
    out = _emit(caplog)
    assert out["message"] == "llm_call"
    assert out["cost_usd"] == "0.0100"
    assert out["stage_run_id"] == "s1"


def test_exception_is_logged_with_traceback(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.ERROR):
        try:
            int("boom")
        except ValueError:
            logging.getLogger("t").exception("failed")
    assert "ValueError" in str(_emit(caplog)["exception"])


def test_configure_logging_sets_level_and_is_idempotent() -> None:
    root = logging.getLogger()
    saved, level = root.handlers[:], root.level
    try:
        configure_logging("warning")
        configure_logging("warning")
        assert root.level == logging.WARNING
        assert len(root.handlers) == 1
    finally:
        root.handlers[:] = saved
        root.setLevel(level)
