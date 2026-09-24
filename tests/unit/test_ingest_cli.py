import pytest
from apps.worker.ingest import parse_args


def test_parse_args_defaults_and_validation() -> None:
    args = parse_args(["hackernews"])
    assert (args.source, args.hours) == ("hackernews", 24)
    assert parse_args(["hackernews", "--hours", "6"]).hours == 6


def test_unknown_source_and_bad_hours_are_rejected() -> None:
    with pytest.raises(SystemExit):
        parse_args(["nope"])
    with pytest.raises(SystemExit):
        parse_args(["hackernews", "--hours", "0"])
