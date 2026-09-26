"""Shared argparse validators for worker CLIs."""

import argparse

MAX_HOURS = 24 * 14


def hours(value: str) -> int:
    parsed = int(value)
    if not 1 <= parsed <= MAX_HOURS:
        raise argparse.ArgumentTypeError(f"must be between 1 and {MAX_HOURS}")
    return parsed


def limit(value: str) -> int:
    parsed = int(value)
    if not 1 <= parsed <= 500:
        raise argparse.ArgumentTypeError("must be between 1 and 500")
    return parsed
