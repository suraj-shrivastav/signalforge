"""Shared argparse validators for worker CLIs."""

import argparse
from collections.abc import Callable

MAX_HOURS = 24 * 14


def hours(value: str) -> int:
    parsed = int(value)
    if not 1 <= parsed <= MAX_HOURS:
        raise argparse.ArgumentTypeError(f"must be between 1 and {MAX_HOURS}")
    return parsed


def bounded_limit(maximum: int) -> Callable[[str], int]:
    """Validator for a ``--limit`` style option, 1 to ``maximum`` inclusive."""

    def parse(value: str) -> int:
        parsed = int(value)
        if not 1 <= parsed <= maximum:
            raise argparse.ArgumentTypeError(f"must be between 1 and {maximum}")
        return parsed

    return parse


limit = bounded_limit(500)

days = bounded_limit(90)
