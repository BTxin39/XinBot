from dataclasses import dataclass
from app.events.base import BaseEvent

@dataclass
class EmotionChangedEvent(BaseEvent):
    old_emotion: str
    new_emotion: str

@dataclass
class MessageReceiveEvent(BaseEvent):
    messge: str