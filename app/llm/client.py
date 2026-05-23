from app.config.runtime import RuntimeConfig
from app.config.validation import validate_config
from app.llm.providers.factory import create_provider

class LLMClient:
    def __init__(self, config: RuntimeConfig | None = None):
        self.config = config or RuntimeConfig.load()
        # 在创建提供商之前验证配置
        validate_config(self.config)
        self.provider = create_provider(
            self.config.provider
        )

    def chat(
            self,
            messages: list[dict],
            model: str,
            temperature: float
    ):
        return self.provider.chat(
            model=model,
            messages=messages,
            temperature=temperature
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