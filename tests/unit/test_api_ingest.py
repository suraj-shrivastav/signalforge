from collections.abc import Iterator
from typing import Any
from uuid import uuid4

import pytest
from apps.api.main import create_app
from apps.api.routes.ingest import get_ingest_runner
from fastapi.testclient import TestClient

from signalforge.core.config import Settings
from signalforge.stages.ingest import IngestResult

DSN = "postgresql://u:p@localhost:5432/db"
TOKEN = "s3cret"


def make_client(*, enabled: bool, calls: list[tuple[str, int]]) -> TestClient:
    kwargs: dict[str, Any] = {"ingest_endpoint_enabled": enabled}
    if enabled:
        kwargs["ingest_token"] = TOKEN
    app = create_app(Settings(_env_file=None, database_url=DSN, **kwargs))  # type: ignore[call-arg,arg-type]

    def runner(source: str, hours: int) -> IngestResult:
        calls.append((source, hours))
        return IngestResult(source=source, fetched=3, inserted=2, stage_run_id=uuid4())

    app.dependency_overrides[get_ingest_runner] = lambda: runner
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def calls() -> list[tuple[str, int]]:
    return []


@pytest.fixture
def client(calls: list[tuple[str, int]]) -> Iterator[TestClient]:
    with make_client(enabled=True, calls=calls) as c:
        yield c


def test_route_does_not_exist_when_the_flag_is_off(calls: list[tuple[str, int]]) -> None:
    with make_client(enabled=False, calls=calls) as c:
        assert c.post("/ingest/hackernews", headers={"X-Ingest-Token": TOKEN}).status_code == 404


@pytest.mark.parametrize("headers", [{}, {"X-Ingest-Token": "wrong"}, {"X-Ingest-Token": ""}])
def test_missing_or_wrong_token_is_401_and_runs_nothing(
    client: TestClient, calls: list[tuple[str, int]], headers: dict[str, str]
) -> None:
    response = client.post("/ingest/hackernews", headers=headers)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"
    assert calls == []


def test_valid_token_runs_ingest(client: TestClient, calls: list[tuple[str, int]]) -> None:
    response = client.post("/ingest/hackernews?hours=6", headers={"X-Ingest-Token": TOKEN})
    assert response.status_code == 200
    assert response.json()["inserted"] == 2
    assert calls == [("hackernews", 6)]


def test_unknown_source_is_404_and_bad_hours_is_422(client: TestClient) -> None:
    headers = {"X-Ingest-Token": TOKEN}
    r = client.post("/ingest/nope", headers=headers)
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "not_found"
    assert client.post("/ingest/hackernews?hours=0", headers=headers).status_code == 422
