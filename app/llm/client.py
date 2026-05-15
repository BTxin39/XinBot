from app.llm.providers.openai_provider import OpenAIProvider

class LLMClient:
    def __init__(self):
        self.provider = OpenAIProvider()

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
