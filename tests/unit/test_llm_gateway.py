# ruff: noqa: ARG002, ARG005
"""Gateway tests. No network: providers are fakes or httpx.MockTransport."""

import logging
import uuid
from decimal import Decimal
from typing import Any

import httpx
import pytest
from pydantic import BaseModel, SecretStr

from signalforge.core.budget import Budget, BudgetLimits, BudgetScope
from signalforge.core.config import Settings
from signalforge.core.errors import (
    ArtifactValidationError,
    BudgetExceededError,
    ProviderRejectedError,
)
from signalforge.db.models import LLMCall
from signalforge.llm.gateway import LLMGateway, build_gateway
from signalforge.llm.providers import FakeProvider, OpenAICompatibleProvider, ProviderReply
from signalforge.llm.registry import register_provider
from signalforge.llm.roles import ModelSpec

RUN = uuid.uuid4()
GOOD = '{"score": 3}'


class Out(BaseModel):
    score: int


class Recorder:
    def __init__(self) -> None:
        self.rows: list[Any] = []

    def add(self, row: Any) -> None:
        self.rows.append(row)


def budget(cap: str = "1") -> Budget:
    return Budget(BudgetScope.TOPIC, BudgetLimits(max_cost_usd=Decimal(cap)))


def gateway(provider: Any, rec: Recorder, b: Budget | None = None, **spec: Any) -> LLMGateway:
    roles = {"r": ModelSpec("m/x", "m", **spec)}
    return LLMGateway(provider, roles, b or budget(), rec)  # type: ignore[arg-type]


def ask(gw: LLMGateway) -> Out:
    return gw.complete_json(role="r", system="s", user="u", schema=Out, stage_run_id=RUN)


def test_valid_reply_parses_and_records_one_row() -> None:
    rec = Recorder()
    out = ask(gateway(FakeProvider([GOOD]), rec))

    assert out.score == 3
    [row] = rec.rows
    assert isinstance(row, LLMCall)
    assert (row.role, row.model, row.model_family, row.succeeded) == ("r", "m/x", "m", True)
    assert row.cost_usd == Decimal(0)


def test_invalid_json_gets_one_repair_retry() -> None:
    rec = Recorder()
    out = ask(gateway(FakeProvider(["nope", GOOD]), rec))

    assert out.score == 3
    assert [r.succeeded for r in rec.rows] == [False, True]


def test_still_invalid_after_repair_raises() -> None:
    rec = Recorder()
    with pytest.raises(ArtifactValidationError):
        ask(gateway(FakeProvider(["nope", "still nope"]), rec))
    assert len(rec.rows) == 2


def test_exhausted_budget_stops_before_any_call() -> None:
    provider = FakeProvider([GOOD])
    with pytest.raises(BudgetExceededError):
        ask(gateway(provider, Recorder(), budget("0")))
    assert provider.chat("m", [], json_mode=True, timeout_s=1).text == GOOD  # untouched


def test_cost_is_decimal_from_per_model_price() -> None:
    class Priced:
        name = "p"

        def chat(self, *a: Any, **k: Any) -> ProviderReply:
            return ProviderReply(GOOD, 1_000_000, 500_000, 5)

    rec = Recorder()
    b = budget()
    ask(
        gateway(
            Priced(),
            rec,
            b,
            input_usd_per_mtok=Decimal("0.10"),
            output_usd_per_mtok=Decimal("0.40"),
        )
    )

    assert rec.rows[0].cost_usd == Decimal("0.30")
    assert b.spent_usd == Decimal("0.30")


def test_reported_cost_wins() -> None:
    class Reports:
        name = "p"

        def chat(self, *a: Any, **k: Any) -> ProviderReply:
            return ProviderReply(GOOD, 1, 1, 1, cost_usd=Decimal("0.0042"))

    rec = Recorder()
    ask(gateway(Reports(), rec, input_usd_per_mtok=Decimal(9), output_usd_per_mtok=Decimal(9)))
    assert rec.rows[0].cost_usd == Decimal("0.0042")


def http_provider(handler: Any, key: str = "sk-secret") -> OpenAICompatibleProvider:
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return OpenAICompatibleProvider("https://x.test/v1/", SecretStr(key), client)


def ok(_: httpx.Request) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "choices": [{"message": {"content": GOOD}}],
            "usage": {"prompt_tokens": 7, "completion_tokens": 2, "cost": 0.001},
        },
    )


def chat(p: OpenAICompatibleProvider) -> ProviderReply:
    return p.chat("m", [{"role": "user", "content": "u"}], json_mode=True, timeout_s=1)


def test_http_request_shape_and_usage() -> None:
    seen: list[httpx.Request] = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(req)
        return ok(req)

    reply = chat(http_provider(handler))

    req = seen[0]
    assert str(req.url) == "https://x.test/v1/chat/completions"
    assert req.headers["Authorization"] == "Bearer sk-secret"
    assert b'"json_object"' in req.content
    assert (reply.input_tokens, reply.output_tokens, reply.cost_usd) == (7, 2, Decimal("0.001"))


@pytest.mark.parametrize("status", [429, 500, 503, 529])
def test_retryable_statuses_are_retried(status: int, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("time.sleep", lambda _: None)
    calls = 0

    def handler(req: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(status, headers={"Retry-After": "0"}, json={})
        return ok(req)

    out = ask(gateway(http_provider(handler), Recorder()))

    assert out.score == 3
    assert calls == 2


@pytest.mark.parametrize("status", [400, 401, 402, 403])
def test_permanent_statuses_are_not_retried(status: int) -> None:
    calls = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(status, json={"error": {"code": status, "message": "bad"}})

    with pytest.raises(ProviderRejectedError):
        chat(http_provider(handler))
    assert calls == 1


def test_key_never_appears_in_errors_or_logs(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG)

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": {"code": 401, "message": "no"}})

    with pytest.raises(ProviderRejectedError) as caught:
        ask(gateway(http_provider(handler), Recorder()))

    assert "sk-secret" not in str(caught.value)
    assert "sk-secret" not in caplog.text
    ask(gateway(http_provider(ok), Recorder()))
    assert "sk-secret" not in caplog.text


def test_a_third_provider_plugs_in_by_registration_alone() -> None:
    class Dummy:
        name = "dummy"

        def chat(self, *a: Any, **k: Any) -> ProviderReply:
            return ProviderReply(GOOD, 1, 1, 1)

        def embed(self, *a: Any, **k: Any) -> Any:
            raise NotImplementedError

    register_provider("dummy", lambda settings: Dummy())
    settings = Settings(  # type: ignore[call-arg]
        _env_file=None,
        database_url="postgresql://u:p@h/db",  # type: ignore[arg-type]
        llm_provider="dummy",
        llm_api_key="k",  # type: ignore[arg-type]
    )
    rec = Recorder()

    gw = build_gateway(settings, rec, budget())  # type: ignore[arg-type]

    out = gw.complete_json(
        role="relevance_filter", system="s", user="u", schema=Out, stage_run_id=RUN
    )
    assert out.score == 3
    assert rec.rows[0].provider == "dummy"
