from app.config.runtime import RuntimeConfig
from app.llm.providers.factory import create_provider
from app.llm.schemas import LLMResponse


class LLMClient:
    def __init__(self, config: RuntimeConfig | None = None):
        self.config = config or RuntimeConfig.load()
        self.provider = create_provider(self.config.provider)

    def chat(
        self,
        messages: list[dict],
        model: str | None = None,
        temperature: float | None = None,
        tools: list[dict] | None = None,
    ) -> LLMResponse:
        return self.provider.chat(
            messages=messages,
            model=model or self.config.model_name,
            temperature=temperature if temperature is not None else self.config.temperature,
            tools=tools,
        )

    def stream_chat(
        self,
        messages: list[dict],
        model: str | None = None,
        temperature: float | None = None,
    ):
        yield from self.provider.stream_chat(
            messages=messages,
            model=model or self.config.model_name,
            temperature=temperature if temperature is not None else self.config.temperature,
        )