from dataclasses import dataclass


@dataclass
class AgentStatus:
    emotion: str
    provider: str
    model_name: str
    memory_messages: int