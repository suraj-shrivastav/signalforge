"""Guard: a logging ``extra`` key that names a LogRecord attribute raises KeyError at runtime.

It only fires when the level is enabled (the CLIs turn INFO on; most tests do not), so a
static scan of every ``extra={...}`` literal in src/ and apps/ catches it in CI.
"""

import ast
import logging
from pathlib import Path

RESERVED = set(logging.makeLogRecord({}).__dict__) | {"message", "asctime"}
ROOT = Path(__file__).resolve().parents[2]


def _extra_keys(tree: ast.AST) -> list[tuple[int, str]]:
    found: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.keyword)
            and node.arg == "extra"
            and isinstance(node.value, ast.Dict)
        ):
            for key in node.value.keys:
                if isinstance(key, ast.Constant) and isinstance(key.value, str):
                    found.append((key.lineno, key.value))
    return found


def test_no_logging_extra_key_shadows_a_logrecord_attribute() -> None:
    clashes = []
    for base in ("src", "apps"):
        for path in (ROOT / base).rglob("*.py"):
            for line, key in _extra_keys(ast.parse(path.read_text())):
                if key in RESERVED:
                    clashes.append(f"{path.relative_to(ROOT)}:{line} extra key {key!r}")
    assert not clashes, "reserved LogRecord names used as extra keys: " + "; ".join(clashes)
