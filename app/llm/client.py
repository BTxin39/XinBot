from app.config.runtime import RuntimeConfig
from app.llm.providers.factory import create_provider

class LLMClient:
    def __init__(self, config: RuntimeConfig | None = None):
        self.config = config or RuntimeConfig.load()
        self.provider = create_provider(
            self.config.provider
        )

    def stream_chat(
            self,
            messages: list[dict],
            model: str,
            temperature: float
    ):
        yield from self.provider.stream_chat(
            model=model,
            messages=messages,
            temperature=temperature,
        )