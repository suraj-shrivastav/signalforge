import httpx
import pytest
from apps.worker import draft, research
from pydantic import SecretStr

from signalforge.core.config import Settings
from signalforge.plugins.search.tavily import TavilyClient

DSN = "postgresql://u:p@localhost:5432/db"


@pytest.mark.parametrize("module", [research, draft])
def test_cli_limit_validation(module: object) -> None:
    parse = module.parse_args  # type: ignore[attr-defined]
    assert parse(["--limit", "50"]).limit == 50
    assert parse([]).limit == 10
    for bad in ("0", "51"):
        with pytest.raises(SystemExit):
            parse(["--limit", bad])


def _settings(key: str | None) -> Settings:
    extra = {} if key is None else {"tavily_api_key": SecretStr(key)}
    return Settings(_env_file=None, database_url=DSN, **extra)  # type: ignore[call-arg,arg-type]


@pytest.mark.parametrize("key", [None, ""])
def test_missing_tavily_key_falls_back_to_primary_only(key: str | None) -> None:
    with httpx.Client() as client:
        search = research.build_search(_settings(key), client)
    assert isinstance(search, research.NoSecondarySearch)
    assert search.search("q", max_results=3) == []


def test_tavily_key_uses_tavily() -> None:
    with httpx.Client() as client:
        assert isinstance(research.build_search(_settings("k"), client), TavilyClient)


def test_draft_retry_failed_flag_defaults_off() -> None:
    assert draft.parse_args([]).retry_failed is False
    assert draft.parse_args(["--retry-failed"]).retry_failed is True
