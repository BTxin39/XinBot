"""Agent 单例管理器 —— FastAPI 与现有 Agent 核心的桥梁。"""

from app.core.agent import Agent
from app.config.runtime import RuntimeConfig


class AgentManager:
    """服务级 Agent 单例。

    所有 HTTP/WS 请求共享同一个 Agent 实例，
    通过 get() 懒加载，reload() 在配置变更后重建。
    """

    _instance: Agent | None = None
    _latest_message: str = ""

    @classmethod
    def get(cls) -> Agent:
        if cls._instance is None:
            cls._instance = Agent(RuntimeConfig.load())
        return cls._instance

    @classmethod
    def reload(cls) -> Agent:
        cls.shutdown()
        cls._instance = Agent(RuntimeConfig.load())
        return cls._instance

    @classmethod
    def shutdown(cls) -> None:
        if cls._instance is not None:
            cls._instance.shutdown()
            cls._instance = None

    @classmethod
    def get_status(cls) -> dict:
        agent = cls.get()
        base = agent.get_status()
        return {
            "emotion": base.emotion,
            "provider": base.provider,
            "model_name": base.model_name,
            "memory_messages": base.memory_messages,
            "persona_name": agent.config.persona_name,
            "latest_message": cls._latest_message,
        }

    @classmethod
    def chat(cls, user_input: str) -> str:
        agent = cls.get()
        parts: list[str] = []
        for chunk in agent.stream_chat(user_input):
            parts.append(chunk)
        reply = "".join(parts)
        cls._latest_message = reply
        return reply

    @classmethod
    def stream_chat(cls, user_input: str):
        agent = cls.get()
        collected: list[str] = []
        for chunk in agent.stream_chat(user_input):
            collected.append(chunk)
            yield chunk
        cls._latest_message = "".join(collected)
