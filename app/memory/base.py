from abc import ABC, abstractmethod

class BaseMemory(ABC):

    @abstractmethod
    def add_message(self, role: str, content: str):
        pass

    @abstractmethod
    def get_message(self) -> list[str]:
        pass

    @abstractmethod
    def clear(self):
        pass