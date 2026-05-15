from abc import ABC, abstractmethod

class BaseStorage(ABC):
    @abstractmethod
    def save(self, data):
        pass

    @abstractmethod
    def load(self):
        pass