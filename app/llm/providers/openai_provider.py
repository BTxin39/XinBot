from openai import OpenAI

from app.config.settings import Settings

from app.llm.schemas import (
    ChatResponse,
)
from app.llm.providers.base import BaseProvider


class OpenAIProvider(BaseProvider):
    def __init__(self):
        self.client = OpenAI(
            api_key=(
                Settings.OPENAI_API_KEY
            ),
            base_url=(
                Settings.OPENAI_BASE_URL
            ),
        )

        # DEPRECATED    
    def chat(
            self,
            messages: list[dict],
            model: str,
            temperature: float
    ) -> str:
        response = self.client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature
        )

        return ChatResponse(
            content=(
                response.choices[0].message.content
            ),
            prompt_tokens=(
                response.usage.prompt_tokens
            ),
            completion_tokens=(
                response.usage.completion_tokens
            ),
            total_tokens=(
                response.usage.total_tokens
            )
        )
        
    def stream_chat(
            self,
            messages: list[dict],
            model: str,
            temperature: float
    ):
        stream = self.client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            stream=True
        )
        
        for chunk in stream:
            delta = chunk.choices[0].delta.content
            if delta:
                yield delta
