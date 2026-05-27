from openai import OpenAI

from app.config.settings import Settings
from app.llm.providers.base import BaseProvider
from app.llm.schemas import LLMResponse


class OpenAIProvider(BaseProvider):
    def __init__(
        self,
        api_key: str | None = Settings.OPENAI_API_KEY,
        base_url: str | None = Settings.OPENAI_BASE_URL,
    ):
        client_kwargs = {"api_key": api_key}
        if base_url:
            client_kwargs["base_url"] = base_url
        self.client = OpenAI(**client_kwargs)

    def chat(
        self,
        messages: list[dict],
        model: str,
        temperature: float,
        tools: list[dict] | None = None,
    ) -> LLMResponse:
        kwargs: dict = dict(
            model=model,
            messages=messages,
            temperature=temperature,
        )
        if tools:
            kwargs["tools"] = tools

        response = self.client.chat.completions.create(**kwargs)
        choice = response.choices[0]
        msg = choice.message

        # DeepSeek 等 thinking 模型会返回 reasoning_content，必须在后续请求中回传
        reasoning_content = getattr(msg, "reasoning_content", None)

        tool_calls = None
        if msg.tool_calls:
            tool_calls = [
                {
                    "id": tc.id,
                    "type": tc.type,
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                for tc in msg.tool_calls
            ]

        return LLMResponse(
            content=msg.content,
            tool_calls=tool_calls,
            reasoning_content=reasoning_content,
        )

    def stream_chat(
        self,
        messages: list[dict],
        model: str,
        temperature: float,
    ):
        stream = self.client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            stream=True,
        )
        for chunk in stream:
            delta = chunk.choices[0].delta.content
            if delta:
                yield delta