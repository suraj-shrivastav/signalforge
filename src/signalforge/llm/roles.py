"""Roles map to models. Stages ask for a role; only this map knows the model."""

from dataclasses import dataclass
from decimal import Decimal

from signalforge.core.config import Settings


@dataclass(frozen=True)
class ModelSpec:
    model_id: str
    family: str
    # None means the price is unknown: cost is then 0 unless the provider reports it.
    input_usd_per_mtok: Decimal | None = None
    output_usd_per_mtok: Decimal | None = None
    # Per-role output cap; None falls back to the provider's global cap.
    max_output_tokens: int | None = None
    timeout_s: float | None = None


RoleMap = dict[str, ModelSpec]


def _spec(
    model: str, max_output_tokens: int | None = None, timeout_s: float | None = None
) -> ModelSpec:
    # Family is the model id's namespace ("vendor/model"); it feeds the
    # writer-vs-judge family check, so it is derived, not configured.
    family = model.split("/", 1)[0] if "/" in model else "unknown"
    return ModelSpec(model, family, max_output_tokens=max_output_tokens, timeout_s=timeout_s)


def build_roles(settings: Settings) -> RoleMap:
    return {
        "relevance_filter": _spec(settings.llm_model_relevance),
        "topic_card": _spec(settings.llm_model_topic_card),
        "research_extraction": _spec(settings.llm_model_research_extraction),
        "claim_embedding": _spec(settings.llm_model_claim_embedding),
        "article_writer": _spec(
            settings.llm_model_article_writer,
            settings.llm_max_output_tokens_article_writer,
            settings.llm_timeout_article_writer_s,
        ),
        "claim_judge": _spec(settings.llm_model_claim_judge),
    }
