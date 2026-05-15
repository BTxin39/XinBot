from abc import ABC, abstractmethod


class BaseCommand(ABC):
    name: str

    @abstractmethod
    def execute(self, *args, **kwargs):
        pass
