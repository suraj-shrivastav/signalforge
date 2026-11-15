"""The one door to an LLM. Stages ask for a role and a schema; nothing else."""

import logging
import time
import uuid
from decimal import Decimal

import httpx
from pydantic import BaseModel, ValidationError
from sqlalchemy.orm import Session

from signalforge.core.budget import Budget
from signalforge.core.config import Settings
from signalforge.core.errors import ArtifactValidationError, ConfigurationError, SignalForgeError
from signalforge.core.logging import log_llm_call
from signalforge.core.retry import call_with_retry
from signalforge.db.models import LLMCall
from signalforge.llm.providers import (
    EmbeddingReply,
    LLMProvider,
    OpenAICompatibleProvider,
    ProviderReply,
)
from signalforge.llm.registry import get_provider
from signalforge.llm.roles import ModelSpec, RoleMap, build_roles, unpriced_models

log = logging.getLogger(__name__)

TIMEOUT_S = 60.0
_MAX_ERROR_CHARS = 500
_MILLION = Decimal(1_000_000)


def _cost(spec: ModelSpec, reply: ProviderReply) -> Decimal:
    if reply.cost_usd is not None:
        return reply.cost_usd
    if spec.input_usd_per_mtok is None or spec.output_usd_per_mtok is None:
        log.warning("unknown model price, recording zero cost", extra={"model": spec.model_id})
        return Decimal(0)
    return (
        spec.input_usd_per_mtok * reply.input_tokens
        + spec.output_usd_per_mtok * reply.output_tokens
    ) / _MILLION


def _embed_cost(spec: ModelSpec, reply: EmbeddingReply) -> Decimal:
    if reply.cost_usd is not None:
        return reply.cost_usd
    if spec.input_usd_per_mtok is None:
        return Decimal(0)
    return spec.input_usd_per_mtok * reply.input_tokens / _MILLION


class LLMGateway:
    def __init__(
        self,
        provider: LLMProvider,
        roles: RoleMap,
        budget: Budget,
        session: Session,
        *,
        role_providers: dict[str, LLMProvider] | None = None,
    ) -> None:
        self._provider = provider
        self._role_providers = role_providers or {}
        self._roles = roles
        self._budget = budget
        self._session = session

    def model_for(self, role: str) -> str:
        try:
            return self._roles[role].model_id
        except KeyError:
            raise ConfigurationError("Unknown LLM role", context={"role": role}) from None

    def family_for(self, role: str) -> str:
        """Model family for ``role``; FR-08's writer-vs-judge check compares these."""
        try:
            return self._roles[role].family
        except KeyError:
            raise ConfigurationError("Unknown LLM role", context={"role": role}) from None

    def complete_json[T: BaseModel](
        self,
        *,
        role: str,
        system: str,
        user: str,
        schema: type[T],
        stage_run_id: uuid.UUID,
    ) -> T:
        """Return a validated ``schema``; one repair retry on invalid output."""
        try:
            spec = self._roles[role]
        except KeyError:
            raise ConfigurationError("Unknown LLM role", context={"role": role}) from None
        messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        error = ""
        for attempt in (1, 2):
            self._budget.check()
            reply = self._chat(role, spec, messages, stage_run_id)
            if reply.finish_reason == "length":
                # A repair retry at the same cap would be cut off again, so fail now.
                self._record(role, spec, reply, stage_run_id, "output truncated at token cap")
                raise ArtifactValidationError(
                    "LLM output truncated at the output token cap",
                    context={"role": role, "output_tokens": reply.output_tokens},
                )
            try:
                result = schema.model_validate_json(reply.text)
            except ValidationError as exc:
                error = f"{exc.error_count()} validation errors"
                self._record(role, spec, reply, stage_run_id, error)
                if attempt == 1:
                    messages = [
                        *messages,
                        {"role": "assistant", "content": reply.text},
                        {
                            "role": "user",
                            "content": "That was not valid JSON for the required schema. "
                            f"Reply with corrected JSON only. Problems: {exc.errors()[:3]}",
                        },
                    ]
                continue
            self._record(role, spec, reply, stage_run_id, None)
            return result
        raise ArtifactValidationError(
            "LLM output failed validation after repair", context={"role": role, "error": error}
        )

    def embed(
        self, *, role: str, texts: list[str], stage_run_id: uuid.UUID
    ) -> list[tuple[float, ...]]:
        """Embed ``texts`` in one batched call; records cost/tokens like ``complete_json``."""
        try:
            spec = self._roles[role]
        except KeyError:
            raise ConfigurationError("Unknown LLM role", context={"role": role}) from None
        self._budget.check()
        reply = call_with_retry(
            lambda: self._provider.embed(spec.model_id, texts, timeout_s=TIMEOUT_S)
        )
        cost = _embed_cost(spec, reply)
        self._budget.record(cost, tokens=reply.input_tokens)
        self._session.add(
            LLMCall(
                stage_run_id=stage_run_id,
                role=role,
                provider=self._provider.name,
                model=spec.model_id,
                model_family=spec.family,
                input_tokens=reply.input_tokens,
                output_tokens=0,
                cost_usd=cost,
                latency_ms=reply.latency_ms,
                succeeded=True,
                error=None,
            )
        )
        return reply.vectors

    def _chat(
        self, role: str, spec: ModelSpec, messages: list[dict[str, str]], stage_run_id: uuid.UUID
    ) -> ProviderReply:
        # Only sent when the role has its own cap, so other providers keep the old call shape.
        extra = {} if spec.max_output_tokens is None else {"max_tokens": spec.max_output_tokens}
        provider = self._role_providers.get(role, self._provider)
        timeout_s = spec.timeout_s or TIMEOUT_S

        def attempt() -> ProviderReply:
            started = time.monotonic()
            try:
                return provider.chat(
                    spec.model_id, messages, json_mode=True, timeout_s=timeout_s, **extra
                )
            except SignalForgeError as exc:
                self._record_failure(role, spec, stage_run_id, exc, started)
                raise

        return call_with_retry(attempt)

    def _record_failure(
        self,
        role: str,
        spec: ModelSpec,
        stage_run_id: uuid.UUID,
        exc: SignalForgeError,
        started: float,
    ) -> None:
        """One failed-attempt row. Error text is the typed error, which never holds secrets."""
        latency_ms = int((time.monotonic() - started) * 1000)
        error = f"{type(exc).__name__}: {exc}"[:_MAX_ERROR_CHARS]
        self._session.add(
            LLMCall(
                stage_run_id=stage_run_id,
                role=role,
                provider=self._provider.name,
                model=spec.model_id,
                model_family=spec.family,
                latency_ms=latency_ms,
                succeeded=False,
                error=error,
            )
        )
        log.warning(
            "llm attempt failed",
            extra={"role": role, "model": spec.model_id, "latency_ms": latency_ms, "error": error},
        )

    def _record(
        self,
        role: str,
        spec: ModelSpec,
        reply: ProviderReply,
        stage_run_id: uuid.UUID,
        error: str | None,
    ) -> None:
        cost = _cost(spec, reply)
        self._budget.record(cost, tokens=reply.input_tokens + reply.output_tokens)
        self._session.add(
            LLMCall(
                stage_run_id=stage_run_id,
                role=role,
                provider=self._provider.name,
                model=spec.model_id,
                model_family=spec.family,
                input_tokens=reply.input_tokens,
                output_tokens=reply.output_tokens,
                cost_usd=cost,
                latency_ms=reply.latency_ms,
                succeeded=error is None,
                error=error,
            )
        )
        log_llm_call(
            log,
            request_id="",
            stage_run_id=str(stage_run_id),
            role=role,
            provider=self._provider.name,
            model=spec.model_id,
            input_tokens=reply.input_tokens,
            output_tokens=reply.output_tokens,
            cost_usd=cost,
            latency_ms=reply.latency_ms,
            success=error is None,
        )


def build_gateway(settings: Settings, session: Session, budget: Budget) -> LLMGateway:
    role_providers: dict[str, LLMProvider] = {}
    if settings.llm_writer_base_url:
        role_providers["article_writer"] = OpenAICompatibleProvider(
            settings.llm_writer_base_url,
            settings.llm_writer_api_key,
            httpx.Client(),
            max_output_tokens=settings.llm_max_output_tokens_article_writer,
        )
    roles = build_roles(settings)
    unpriced = unpriced_models(roles)
    if unpriced:
        log.warning("models without a configured price; their cost reads 0: %s", unpriced)
    return LLMGateway(
        get_provider(settings),
        roles,
        budget,
        session,
        role_providers=role_providers,
    )
