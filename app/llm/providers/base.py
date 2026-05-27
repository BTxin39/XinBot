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
    ):
        pass
