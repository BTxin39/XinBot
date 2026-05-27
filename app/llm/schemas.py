from dataclasses import dataclass, field


@dataclass
class LLMResponse:
    content: str | None = None
    tool_calls: list[dict] | None = None
    reasoning_content: str | None = None