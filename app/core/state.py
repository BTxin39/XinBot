from dataclasses import dataclass


# ❗ Emotions 数据已迁移到 data/personas.json，由 PersonaStore 统一管理。
# 此处只保留 AgentState 数据类。


@dataclass
class AgentState:
    emotion: str = "normal"
    energy: int = 100
