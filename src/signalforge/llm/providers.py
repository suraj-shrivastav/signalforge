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


class LLMProvider(Protocol):
    name: str

    def chat(
        self,
        model: str,
        messages: list[dict[str, str]],
        *,
        json_mode: bool,
        timeout_s: float,
    ) -> ProviderReply: ...


class FakeProvider:
    """Returns queued replies with zero cost. No network."""

    name = "fake"

    def __init__(self, replies: list[str]) -> None:
        self._replies = list(replies)

    def chat(
        self,
        model: str,
        messages: list[dict[str, str]],
        *,
        json_mode: bool,
        timeout_s: float,
    ) -> ProviderReply:
        if not self._replies:
            raise ProviderRejectedError("FakeProvider has no queued replies")
        return ProviderReply(self._replies.pop(0), input_tokens=0, output_tokens=0, latency_ms=0)


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
    ) -> None:
        self._url = base_url.rstrip("/") + "/chat/completions"
        self._api_key = api_key
        self._client = client
        self._extra_headers = extra_headers or {}
        self._extra_body = extra_body or {}

    def chat(
        self,
        model: str,
        messages: list[dict[str, str]],
        *,
        json_mode: bool,
        timeout_s: float,
    ) -> ProviderReply:
        headers = dict(self._extra_headers)
        if self._api_key is not None:
            headers["Authorization"] = f"Bearer {self._api_key.get_secret_value()}"
        body: dict[str, Any] = {"model": model, "messages": messages}
        if json_mode:
            body["response_format"] = {"type": "json_object"}
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

    @staticmethod
    def _parse(response: httpx.Response, latency_ms: int) -> ProviderReply:
        try:
            data = response.json()
            text = data["choices"][0]["message"]["content"]
            usage = data.get("usage") or {}
            cost = usage.get("cost")
            return ProviderReply(
                text=str(text),
                input_tokens=int(usage.get("prompt_tokens", 0)),
                output_tokens=int(usage.get("completion_tokens", 0)),
                latency_ms=latency_ms,
                cost_usd=Decimal(str(cost)) if cost is not None else None,
            )
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise ProviderUnavailableError("LLM provider returned a malformed reply") from exc
