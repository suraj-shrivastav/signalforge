"""Roles map to models. Stages ask for a role; only this map knows the model."""

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal

from signalforge.core.config import ModelPrice, Settings


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
    model: str,
    prices: Mapping[str, ModelPrice],
    max_output_tokens: int | None = None,
    timeout_s: float | None = None,
) -> ModelSpec:
    # Family is the model id's namespace ("vendor/model"); it feeds the
    # writer-vs-judge family check, so it is derived, not configured.
    family = model.split("/", 1)[0] if "/" in model else "unknown"
    price = prices.get(model)
    return ModelSpec(
        model,
        family,
        input_usd_per_mtok=price.input if price else None,
        output_usd_per_mtok=price.output if price else None,
        max_output_tokens=max_output_tokens,
        timeout_s=timeout_s,
    )


def unpriced_models(roles: RoleMap) -> list[str]:
    """Model ids with no configured price: their cost reads 0."""
    return sorted({s.model_id for s in roles.values() if s.input_usd_per_mtok is None})


def build_roles(settings: Settings) -> RoleMap:
    return {
        "relevance_filter": _spec(settings.llm_model_relevance, settings.llm_prices),
        "topic_card": _spec(settings.llm_model_topic_card, settings.llm_prices),
        "research_extraction": _spec(settings.llm_model_research_extraction, settings.llm_prices),
        "claim_embedding": _spec(settings.llm_model_claim_embedding, settings.llm_prices),
        "article_writer": _spec(
            settings.llm_model_article_writer,
            settings.llm_prices,
            settings.llm_max_output_tokens_article_writer,
            settings.llm_timeout_article_writer_s,
        ),
        "claim_judge": _spec(settings.llm_model_claim_judge, settings.llm_prices),
    }
