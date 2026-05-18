import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path


REGISTRY_PATH = Path("data/llm_registry.json")


@dataclass
class ProviderConfig:
    name: str
    provider_type: str
    api_key_env: str
    base_url: str | None = None
    base_url_env: str | None = None

    @property
    def api_key(self) -> str | None:
        return os.getenv(self.api_key_env)

    @property
    def resolved_base_url(self) -> str | None:
        if self.base_url_env is None:
            return self.base_url
        return os.getenv(self.base_url_env)


@dataclass
class ModelConfig:
    name: str
    provider: str


def _default_registry() -> dict:
    return {
        "providers": [
            {
                "name": "openai",
                "provider_type": "openai-compatible",
                "api_key_env": "OPENAI_API_KEY",
                "base_url": None,
            },
            {
                "name": "deepseek",
                "provider_type": "openai-compatible",
                "api_key_env": "deepseek_api_key",
                "base_url": "https://api.deepseek.com/",
            },
        ],
        "models": [
            {
                "name": "gpt-4o-mini",
                "provider": "openai",
            },
            {
                "name": "deepseek-v4-flash",
                "provider": "deepseek",
            },
        ],
    }


class LLMRegistry:
    def __init__(self, path: Path = REGISTRY_PATH):
        self.path = path
        self.data = self._load()

    def _load(self) -> dict:
        if not self.path.exists():
            return _default_registry()

        with open(self.path, "r", encoding="utf-8") as f:
            return json.load(f)

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)

    def list_providers(self) -> list[ProviderConfig]:
        return [
            ProviderConfig(**provider)
            for provider in self.data.get("providers", [])
        ]

    def get_provider(
        self,
        provider_name: str,
    ) -> ProviderConfig | None:
        for provider in self.list_providers():
            if provider.name == provider_name:
                return provider
        return None

    def add_provider(
        self,
        provider: ProviderConfig,
    ) -> None:
        if self.get_provider(provider.name):
            raise ValueError(
                f"Provider already exists: {provider.name}"
            )
        self.data.setdefault("providers", []).append(
            asdict(provider)
        )
        self.save()

    def remove_provider(
        self,
        provider_name: str,
    ) -> None:
        if self.models_for_provider(provider_name):
            raise ValueError(
                "Provider still has models. "
                "Remove those models first."
            )

        providers = self.data.get("providers", [])
        self.data["providers"] = [
            provider
            for provider in providers
            if provider.get("name") != provider_name
        ]
        self.save()

    def list_models(self) -> list[ModelConfig]:
        return [
            ModelConfig(**model)
            for model in self.data.get("models", [])
        ]

    def get_model(
        self,
        model_name: str,
    ) -> ModelConfig | None:
        for model in self.list_models():
            if model.name == model_name:
                return model
        return None

    def models_for_provider(
        self,
        provider_name: str,
    ) -> list[ModelConfig]:
        return [
            model
            for model in self.list_models()
            if model.provider == provider_name
        ]

    def add_model(self, model: ModelConfig) -> None:
        if self.get_model(model.name):
            raise ValueError(
                f"Model already exists: {model.name}"
            )
        if self.get_provider(model.provider) is None:
            raise ValueError(
                f"Unknown provider: {model.provider}"
            )
        self.data.setdefault("models", []).append(
            asdict(model)
        )
        self.save()

    def remove_model(self, model_name: str) -> None:
        models = self.data.get("models", [])
        self.data["models"] = [
            model
            for model in models
            if model.get("name") != model_name
        ]
        self.save()
