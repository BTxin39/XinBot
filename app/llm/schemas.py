from dataclasses import dataclass, field


@dataclass
class LLMResponse:
    content: str | None = None
    tool_calls: list[dict] | None = None
    reasoning_content: str | None = None


@dataclass
class StreamEvent:
    """流式对话的单个事件。

    为什么需要事件类型而不是直接 yield 字符串：
    流式响应里可能**先出文本、后出工具调用**，也可能只出工具调用。
    调用方必须能区分"这是一段可显示的文字"和"这一轮要调用工具"，
    否则会把工具参数当正文打印出来。
    """

    kind: str  # "delta" | "tool_calls"
    text: str = ""
    tool_calls: list[dict] = field(default_factory=list)
    reasoning_content: str | None = None

    @classmethod
    def delta(cls, text: str) -> "StreamEvent":
        return cls(kind="delta", text=text)

    @classmethod
    def tools(cls, tool_calls: list[dict], content: str = "") -> "StreamEvent":
        return cls(kind="tool_calls", tool_calls=tool_calls, text=content)
