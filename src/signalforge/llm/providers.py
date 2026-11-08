# ruff: noqa: ARG002
"""Provider implementations. Providers are plug-ins; see ``registry.py``."""

import logging
import time
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Protocol

import httpx
from pydantic import SecretStr

from signalforge.core.errors import (
    OperationTimeoutError,
    ProviderRejectedError,
    ProviderUnavailableError,
    RateLimitedError,
)

log = logging.getLogger(__name__)

_RETRYABLE_STATUS = {500, 502, 503, 524, 529}


@dataclass(frozen=True)
class ProviderReply:
    text: str
    input_tokens: int
    output_tokens: int
    latency_ms: int
    # Set only when the provider reports what the call cost.
    cost_usd: Decimal | None = None
    # Why generation stopped ('stop', 'length', ...); 'length' means the reply was cut off.
    finish_reason: str | None = None


@dataclass(frozen=True)
class EmbeddingReply:
    vectors: list[tuple[float, ...]]
    input_tokens: int
    latency_ms: int
    cost_usd: Decimal | None = None


class LLMProvider(Protocol):
    name: str

    def chat(
        self,
        model: str,
        messages: list[dict[str, str]],
        *,
        json_mode: bool,
        timeout_s: float,
        max_tokens: int | None = None,
    ) -> ProviderReply: ...

    def embed(self, model: str, texts: list[str], *, timeout_s: float) -> EmbeddingReply: ...


class FakeProvider:
    """Returns queued replies with zero cost. No network."""

    name = "fake"

    def __init__(
        self, replies: list[str], embeddings: list[list[tuple[float, ...]]] | None = None
    ) -> None:
        self._replies = list(replies)
        self._embeddings = list(embeddings or [])

    def chat(
        self,
        model: str,
        messages: list[dict[str, str]],
        *,
        json_mode: bool,
        timeout_s: float,
        max_tokens: int | None = None,
    ) -> ProviderReply:
        if not self._replies:
            raise ProviderRejectedError("FakeProvider has no queued replies")
        return ProviderReply(self._replies.pop(0), input_tokens=0, output_tokens=0, latency_ms=0)

    def embed(self, model: str, texts: list[str], *, timeout_s: float) -> EmbeddingReply:
        if not self._embeddings:
            # No queued vectors: give every text the same embedding, which merges them all.
            return EmbeddingReply([(1.0, 0.0)] * len(texts), input_tokens=0, latency_ms=0)
        vectors = self._embeddings.pop(0)
        return EmbeddingReply(vectors, input_tokens=0, latency_ms=0)


def _error_message(response: httpx.Response) -> str:
    try:
        body = response.json()
        return str(body["error"]["message"])[:200]
    except (ValueError, KeyError, TypeError):
        return "no error detail"


class OpenAICompatibleProvider:
    """Any API that speaks ``POST {base_url}/chat/completions`` with a Bearer key."""

    name = "openai_compatible"

    def __init__(
        self,
        base_url: str,
        api_key: SecretStr | None,
        client: httpx.Client,
        *,
        extra_headers: dict[str, str] | None = None,
        extra_body: dict[str, Any] | None = None,
        max_output_tokens: int | None = None,
        embed_extra_body: dict[str, Any] | None = None,
        embed_batch_size: int = 0,
    ) -> None:
        # Without a cap, routers such as OpenRouter reserve credit for the model's full
        # output window and reject the call, and one runaway reply can blow a budget.
        self._max_output_tokens = max_output_tokens
        self._url = base_url.rstrip("/") + "/chat/completions"
        self._embed_url = base_url.rstrip("/") + "/embeddings"
        self._api_key = api_key
        self._client = client
        self._extra_headers = extra_headers or {}
        self._extra_body = extra_body or {}
        self._embed_extra_body = embed_extra_body or {}
        # 0 sends every text in one request. Some hosted embedding models answer HTTP 500 to
        # any batch above 1 text (seen with NVIDIA's nemotron embed), so 1 is a valid setting.
        self._embed_batch_size = embed_batch_size

    def chat(
        self,
        model: str,
        messages: list[dict[str, str]],
        *,
        json_mode: bool,
        timeout_s: float,
        max_tokens: int | None = None,
    ) -> ProviderReply:
        headers = dict(self._extra_headers)
        if self._api_key is not None:
            headers["Authorization"] = f"Bearer {self._api_key.get_secret_value()}"
        body: dict[str, Any] = {"model": model, "messages": messages}
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        cap = max_tokens if max_tokens is not None else self._max_output_tokens
        if cap is not None:
            body["max_tokens"] = cap
        body.update(self._extra_body)

        started = time.monotonic()
        try:
            response = self._client.post(self._url, json=body, headers=headers, timeout=timeout_s)
        except httpx.TimeoutException as exc:
            raise OperationTimeoutError("LLM request timed out") from exc
        except httpx.HTTPError as exc:
            raise ProviderUnavailableError("LLM request failed") from exc
        latency_ms = int((time.monotonic() - started) * 1000)

        status = response.status_code
        if status == 429:
            retry_after = response.headers.get("Retry-After")
            raise RateLimitedError(
                "LLM provider rate limited",
                retry_after_seconds=float(retry_after)
                if retry_after and retry_after.replace(".", "", 1).isdigit()
                else None,
            )
        if status in _RETRYABLE_STATUS:
            raise ProviderUnavailableError("LLM provider unavailable", context={"status": status})
        if status >= 400:
            raise ProviderRejectedError(
                "LLM provider rejected the request",
                context={"status": status, "detail": _error_message(response)},
            )
        return self._parse(response, latency_ms)

    def embed(self, model: str, texts: list[str], *, timeout_s: float) -> EmbeddingReply:
        size = self._embed_batch_size
        if size <= 0 or len(texts) <= size:
            return self._embed_batch(model, texts, timeout_s=timeout_s)
        replies = [
            self._embed_batch(model, texts[i : i + size], timeout_s=timeout_s)
            for i in range(0, len(texts), size)
        ]
        return EmbeddingReply(
            vectors=[v for reply in replies for v in reply.vectors],
            input_tokens=sum(r.input_tokens for r in replies),
            latency_ms=sum(r.latency_ms for r in replies),
        )

    def _embed_batch(self, model: str, texts: list[str], *, timeout_s: float) -> EmbeddingReply:
        headers = dict(self._extra_headers)
        if self._api_key is not None:
            headers["Authorization"] = f"Bearer {self._api_key.get_secret_value()}"
        body: dict[str, Any] = {"model": model, "input": texts, **self._embed_extra_body}

        started = time.monotonic()
        try:
            response = self._client.post(
                self._embed_url, json=body, headers=headers, timeout=timeout_s
            )
        except httpx.TimeoutException as exc:
            raise OperationTimeoutError("LLM request timed out") from exc
        except httpx.HTTPError as exc:
            raise ProviderUnavailableError("LLM request failed") from exc
        latency_ms = int((time.monotonic() - started) * 1000)

        status = response.status_code
        if status == 429:
            retry_after = response.headers.get("Retry-After")
            raise RateLimitedError(
                "LLM provider rate limited",
                retry_after_seconds=float(retry_after)
                if retry_after and retry_after.replace(".", "", 1).isdigit()
                else None,
            )
        if status in _RETRYABLE_STATUS:
            raise ProviderUnavailableError("LLM provider unavailable", context={"status": status})
        if status >= 400:
            raise ProviderRejectedError(
                "LLM provider rejected the request",
                context={"status": status, "detail": _error_message(response)},
            )
        try:
            data = response.json()
            vectors = [tuple(float(x) for x in item["embedding"]) for item in data["data"]]
            usage = data.get("usage") or {}
            return EmbeddingReply(
                vectors=vectors,
                input_tokens=int(usage.get("prompt_tokens", 0)),
                latency_ms=latency_ms,
            )
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise ProviderUnavailableError("LLM provider returned a malformed reply") from exc

    @staticmethod
    def _parse(response: httpx.Response, latency_ms: int) -> ProviderReply:
        try:
            data = response.json()
            text = data["choices"][0]["message"]["content"]
            usage = data.get("usage") or {}
            cost = usage.get("cost")
            finish = data["choices"][0].get("finish_reason")
            return ProviderReply(
                text=str(text),
                input_tokens=int(usage.get("prompt_tokens", 0)),
                output_tokens=int(usage.get("completion_tokens", 0)),
                latency_ms=latency_ms,
                cost_usd=Decimal(str(cost)) if cost is not None else None,
                finish_reason=str(finish) if finish is not None else None,
            )
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise ProviderUnavailableError("LLM provider returned a malformed reply") from exc
