from typing import Any

import pytest
from pydantic import ValidationError

from signalforge.core.config import Settings

DSN = "postgresql://u:p@localhost:5432/db"


def build(**kw: Any) -> Settings:
    return Settings(_env_file=None, database_url=DSN, **kw)  # type: ignore[call-arg,arg-type]


def test_endpoint_is_off_by_default() -> None:
    assert build().ingest_endpoint_enabled is False


def test_enabling_the_endpoint_requires_a_token() -> None:
    with pytest.raises(ValidationError, match="INGEST_TOKEN"):
        build(ingest_endpoint_enabled=True)
    with pytest.raises(ValidationError, match="INGEST_TOKEN"):
        build(ingest_endpoint_enabled=True, ingest_token="")
    assert build(ingest_endpoint_enabled=True, ingest_token="s3cret").ingest_endpoint_enabled


def test_token_is_not_exposed_in_repr() -> None:
    assert "s3cret" not in repr(build(ingest_token="s3cret"))
