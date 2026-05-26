from abc import ABC, abstractmethod

class BaseProvider(ABC):
    @abstractmethod
    def stream_chat(
        self,
        messages,
        model,
        temperature,
    ):
        pass
