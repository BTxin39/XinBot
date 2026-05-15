from abc import ABC, abstractmethod

class BaseProvider(ABC):
    @abstractmethod
    def chat(
        self,
        messages,
        model,
        temperature,
    ):
        pass

    @abstractmethod
    def stream_chat(
        self,
        messages,
        model,
        temperature,
    ):
        pass
