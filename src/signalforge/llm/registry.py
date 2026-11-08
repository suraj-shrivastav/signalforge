"""Provider registry. ``register_provider`` is the only extension point."""

from collections.abc import Callable

import httpx

from signalforge.core.config import Settings
from signalforge.core.errors import ConfigurationError
from signalforge.llm.providers import FakeProvider, LLMProvider, OpenAICompatibleProvider

ProviderFactory = Callable[[Settings], LLMProvider]

PROVIDERS: dict[str, ProviderFactory] = {}


def register_provider(name: str, factory: ProviderFactory) -> None:
    PROVIDERS[name] = factory


def get_provider(settings: Settings) -> LLMProvider:
    try:
        factory = PROVIDERS[settings.llm_provider]
    except KeyError:
        raise ConfigurationError(
            "Unknown LLM provider",
            context={"provider": settings.llm_provider, "known": sorted(PROVIDERS)},
        ) from None
    return factory(settings)


def _fake(_settings: Settings) -> LLMProvider:
    return FakeProvider([])


def _openai_compatible(settings: Settings) -> LLMProvider:
    if not settings.llm_base_url:
        raise ConfigurationError("LLM_BASE_URL is required for openai_compatible")
    return OpenAICompatibleProvider(
        settings.llm_base_url,
        settings.llm_api_key,
        httpx.Client(),
        extra_body=settings.llm_extra_body,
        embed_extra_body=settings.llm_embed_extra_body,
        embed_batch_size=settings.llm_embed_batch_size,
        max_output_tokens=settings.llm_max_output_tokens,
    )


register_provider("fake", _fake)
register_provider("openai_compatible", _openai_compatible)
