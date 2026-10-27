from abc import ABC, abstractmethod

from app.llm.schemas import LLMResponse


class BaseProvider(ABC):
    @abstractmethod
    def chat(
        self,
        messages: list[dict],
        model: str,
        temperature: float,
        tools: list[dict] | None = None,
    ) -> LLMResponse:
        pass

    @abstractmethod
    def stream_chat(
        self,
        messages: list[dict],
        model: str,
        temperature: float,
        tools: list[dict] | None = None,
    ):
        """流式对话，逐条 yield `StreamEvent`。

        必须支持 `tools`：否则一旦模型要调用工具，流式路径就没法用，
        只能退回"整段等待"，桌宠气泡就失去逐字效果。
        """
        pass
