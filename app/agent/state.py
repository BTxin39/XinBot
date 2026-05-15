from dataclasses import dataclass

@dataclass
class AgentState:
    emotion: str = "normal"
    energy: int = 100