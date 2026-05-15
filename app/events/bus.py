from collections import defaultdict
from typing import Callable


class EventBus:
    def __init__(self):
        self.listeners = defaultdict(list)

    def subscribe(
        self,
        event_type,
        listener: Callable,
    ):
        self.listeners[event_type].append(
            listener
        )

    def emit(
        self,
        event,
    ):
        event_type = type(event)

        for listener in self.listeners[
            event_type
        ]:
            listener(event)