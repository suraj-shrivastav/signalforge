import pytest
from apps.worker.cards import parse_args


def test_cli_limit_validation() -> None:
    assert parse_args(["--limit", "200"]).limit == 200
    for bad in ("0", "201"):
        with pytest.raises(SystemExit):
            parse_args(["--limit", bad])
