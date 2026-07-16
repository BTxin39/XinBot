"""公用会话循环：CLI 和 Web 共用的 Agent 对话驱动。"""

from typing import Callable, Protocol

from app.core.agent import Agent
from app.commands.handler import CommandHandler


class SessionUI(Protocol):
    """会话 UI 接口。CLI / Web 各自实现。"""

    def on_start(self, agent: Agent) -> None:
        """会话启动时调用。"""
        ...

    def on_before_reply(self, agent: Agent, user_input: str) -> None:
        """用户输入后、Agent 回复前调用。"""
        ...

    def on_chunk(self, agent: Agent, chunk: str) -> None:
        """流式回复的每个 token。"""
        ...

    def on_after_reply(self, agent: Agent, full_response: str) -> None:
        """一轮回复结束后调用。"""
        ...


class SessionRunner:
    """驱动 Agent 对话循环，与 UI 实现解耦。

    CLI 用法::

        runner = SessionRunner(agent_factory=lambda: Agent(config))
        runner.run(DesktopPetUI(console))

    Web 用法::

        runner = SessionRunner(agent_factory=lambda: Agent(config))
        runner.chat_once(user_input)
    """

    def __init__(self, agent_factory: Callable[[], Agent]):
        self._agent_factory = agent_factory
        self._agent: Agent | None = None
        self._command_handler: CommandHandler | None = None

    @property
    def agent(self) -> Agent:
        assert self._agent is not None, "Agent 尚未初始化，请先调用 init()"
        return self._agent

    def init(self) -> None:
        """初始化 Agent 和命令处理器。"""
        self._agent = self._agent_factory()
        self._command_handler = CommandHandler(self._agent)

    def shutdown(self) -> str:
        """保存记忆并关闭 Agent。返回记忆保存结果字符串。"""
        assert self._agent is not None
        try:
            result = self._agent.remember_now()
            self._agent.shutdown()
            return result
        except Exception as e:
            self._agent.shutdown()
            return f"记忆保存失败: {e}"

    def handle_command(self, user_input: str) -> bool:
        """尝试处理命令；返回 True 表示已处理。"""
        assert self._command_handler is not None
        return self._command_handler.handle(user_input)

    def chat_once(self, user_input: str):
        """单次流式对话：yield chunk，不含命令处理和记忆保存。

        Web 端可直接用这个方法驱动流式输出。
        """
        assert self._agent is not None
        for chunk in self._agent.stream_chat(user_input=user_input):
            yield chunk

    def run(self, ui: SessionUI) -> None:
        """启动 CLI 对话循环（阻塞）。

        CLI 端调用此方法；Web 端应使用 chat_once() 自行驱动。
        """
        self.init()
        assert self._agent is not None
        assert self._command_handler is not None

        ui.on_start(self._agent)

        while True:
            user_input = input("\nYou: ")
            if user_input.lower() in ("exit", "quit"):
                result = self.shutdown()
                print(f"\n{result or '记忆已保存.'}")
                break

            if self._command_handler.handle(user_input):
                ui.on_start(self._agent)
                continue

            ui.on_before_reply(self._agent, user_input)
            full_response = ""
            for chunk in self._agent.stream_chat(user_input=user_input):
                full_response += chunk
                ui.on_chunk(self._agent, chunk)
            ui.on_after_reply(self._agent, full_response)
