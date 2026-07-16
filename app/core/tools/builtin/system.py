"""内置系统工具。"""

from datetime import datetime

from app.core.tools.base import BaseTool, DangerLevel, ToolParameter
from app.core.persona import PersonaStore


class GetTimeTool(BaseTool):
    name = "get_time"
    description = "获取当前的日期和时间"
    parameters = []
    danger_level = DangerLevel.SAFE

    def execute(self, **kwargs) -> str:
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class SetEmotionTool(BaseTool):
    name = "set_emotion"
    description = "改变 AI 桌宠的情绪状态。"

    parameters = [
        ToolParameter(
            name="emotion",
            type="string",
            description="要设置的情绪",
            enum=list(PersonaStore.get().emotions.keys()),
        )
    ]
    danger_level = DangerLevel.SAFE

    def __init__(self, agent):
        self.agent = agent

    def execute(self, emotion: str) -> str:
        valid = set(PersonaStore.get().emotions.keys())
        if emotion not in valid:
            return f"无效情绪: {emotion}。可选: {', '.join(sorted(valid))}"
        self.agent.change_emotion(emotion)
        return f"情绪已切换为 {emotion}"


class GetStatusTool(BaseTool):
    name = "get_status"
    description = "获取 AI 桌宠的当前状态，包括情绪、使用的模型、记忆数量"

    parameters = []
    danger_level = DangerLevel.SAFE

    def __init__(self, agent):
        self.agent = agent

    def execute(self, **kwargs) -> str:
        status = self.agent.get_status()
        return (
            f"当前情绪: {status.emotion}\n"
            f"模型: {status.model_name}\n"
            f"记忆消息数: {status.memory_messages}"
        )
