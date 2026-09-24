from collections.abc import Iterator
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from apps.api.deps import get_signal_repository
from apps.api.main import create_app
from fastapi.testclient import TestClient

from signalforge.core.config import Settings
from signalforge.core.errors import ArtifactValidationError, ProviderUnavailableError

DSN = "postgresql://u:p@localhost:5432/db"


def fake_signal() -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(),
        source="hackernews",
        source_type="community",
        canonical_url="https://example.com/a",
        title="A title",
        published_at=datetime(2026, 9, 24, tzinfo=UTC),
        summary="",
        metadata_={"points": 50},
    )


class FakeRepo:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.calls: list[dict[str, object]] = []

    def list_page(self, **kwargs: object) -> SimpleNamespace:
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return SimpleNamespace(items=[fake_signal()], next_cursor="next")


@pytest.fixture
def repo() -> FakeRepo:
    return FakeRepo()


@pytest.fixture
def client(repo: FakeRepo) -> Iterator[TestClient]:
    app = create_app(Settings(_env_file=None, database_url=DSN))  # type: ignore[call-arg,arg-type]
    app.dependency_overrides[get_signal_repository] = lambda: repo
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client


def test_health(client: TestClient) -> None:
    assert client.get("/health").json() == {"status": "ok"}


def test_list_signals_returns_items_and_cursor(client: TestClient, repo: FakeRepo) -> None:
    body = client.get("/signals?limit=5&source=hackernews").json()
    assert body["next_cursor"] == "next"
    assert body["items"][0]["title"] == "A title"
    assert body["items"][0]["metadata"] == {"points": 50}
    assert repo.calls == [{"limit": 5, "cursor": None, "source": "hackernews"}]


@pytest.mark.parametrize("query", ["limit=0", "limit=101", "limit=abc"])
def test_bad_limit_is_a_422_with_the_standard_error_shape(client: TestClient, query: str) -> None:
    response = client.get(f"/signals?{query}")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_invalid_cursor_maps_to_422(repo: FakeRepo, client: TestClient) -> None:
    repo.error = ArtifactValidationError("Invalid cursor")
    response = client.get("/signals?cursor=zzz")
    assert response.status_code == 422
    assert response.json()["error"] == {
        "code": "validation_error",
        "message": "Invalid cursor",
        "correlation_id": response.headers["X-Request-ID"],
    }


def test_retryable_error_is_a_503(repo: FakeRepo, client: TestClient) -> None:
    repo.error = ProviderUnavailableError("db down")
    assert client.get("/signals").status_code == 503


def test_unexpected_error_is_a_500_that_leaks_nothing(repo: FakeRepo, client: TestClient) -> None:
    repo.error = RuntimeError("secret internals")
    response = client.get("/signals", headers={"X-Request-ID": "req-500"})
    assert response.status_code == 500
    assert "secret internals" not in response.text
    assert response.json()["error"] == {
        "code": "internal_error",
        "message": "Internal error",
        "correlation_id": "req-500",
    }
    assert response.headers["X-Request-ID"] == "req-500"


def test_unknown_route_uses_the_same_error_shape(client: TestClient) -> None:
    response = client.get("/nope")
    assert response.status_code == 404
    assert set(response.json()["error"]) == {"code", "message", "correlation_id"}


def test_request_id_is_echoed_when_safe_and_replaced_when_not(client: TestClient) -> None:
    safe = client.get("/health", headers={"X-Request-ID": "abc-123"})
    assert safe.headers["X-Request-ID"] == "abc-123"
    replaced = client.get("/health", headers={"X-Request-ID": "bad id with spaces"})
    assert replaced.headers["X-Request-ID"] != "bad id with spaces"
