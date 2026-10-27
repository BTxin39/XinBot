from openai import OpenAI

from app.config.settings import Settings
from app.llm.providers.base import BaseProvider
from app.llm.schemas import LLMResponse, StreamEvent


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
        tools: list[dict] | None = None,
    ):
        """流式对话，yield StreamEvent。

        工具调用在流式响应里是**分片**到达的（同一个 index 会来多个
        `function.arguments` 片段），必须按 index 累积后再一次性交给调用方；
        直接拼接字符串会把多个工具的参数混在一起。
        """
        kwargs: dict = dict(
            model=model,
            messages=messages,
            temperature=temperature,
            stream=True,
        )
        if tools:
            kwargs["tools"] = tools

        stream = self.client.chat.completions.create(**kwargs)
        pending: dict[int, dict] = {}
        reasoning_parts: list[str] = []

        for chunk in stream:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta

            content = getattr(delta, "content", None)
            if content:
                yield StreamEvent.delta(content)

            # thinking 模型：reasoning_content 也要收集，后续要回传
            piece = getattr(delta, "reasoning_content", None)
            if piece:
                reasoning_parts.append(piece)

            for call in getattr(delta, "tool_calls", None) or []:
                index = call.index if call.index is not None else 0
                slot = pending.setdefault(
                    index,
                    {"id": "", "type": "function",
                     "function": {"name": "", "arguments": ""}},
                )
                if call.id:
                    slot["id"] = call.id
                function = getattr(call, "function", None)
                if function is not None:
                    if function.name:
                        slot["function"]["name"] = function.name
                    if function.arguments:
                        slot["function"]["arguments"] += function.arguments

        if pending:
            yield StreamEvent(
                kind="tool_calls",
                tool_calls=[pending[key] for key in sorted(pending)],
                reasoning_content="".join(reasoning_parts) or None,
            )