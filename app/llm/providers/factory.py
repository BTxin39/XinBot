from app.llm.providers.base import BaseProvider
from app.llm.providers.openai_provider import OpenAIProvider
from app.llm.registry import LLMRegistry, ProviderConfig


SUPPORTED_PROVIDER_TYPES = {
    "openai-compatible": OpenAIProvider,
    "ollama": OpenAIProvider,
}


def create_provider(provider_name: str) -> BaseProvider:
    registry = LLMRegistry()
    provider_config = registry.get_provider(
        provider_name
    )
    if provider_config is None:
        supported = ", ".join(list_providers())
        raise ValueError(
            f"Unsupported provider: {provider_name}. "
            f"Supported providers: {supported}"
        )

    return create_provider_from_config(
        provider_config
    )


def create_provider_from_config(
    provider_config: ProviderConfig,
) -> BaseProvider:
    provider_class = SUPPORTED_PROVIDER_TYPES.get(
        provider_config.provider_type
    )
    if provider_class is None:
        supported = ", ".join(
            sorted(SUPPORTED_PROVIDER_TYPES)
        )
        raise ValueError(
            "Unsupported provider type: "
            f"{provider_config.provider_type}. "
            f"Supported types: {supported}"
        )

    return provider_class(
        api_key=provider_config.api_key or ("ollama" if provider_config.provider_type == "ollama" else None),
        base_url=provider_config.resolved_base_url,
    )


def list_providers() -> list[str]:
    return [
        provider.name
        for provider in LLMRegistry().list_providers()
    ]


def list_provider_types() -> list[str]:
    return sorted(SUPPORTED_PROVIDER_TYPES)
