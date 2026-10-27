"""公用会话驱动：CLI 与 Web 共用的 Agent 对话循环骨架。

原位置 `app/core/session.py` 有两个问题（见 docs/DECISIONS/DECISIONS_V0.2.0.md §7、§2.4）：
    1. 领域层 `core/` 反向 import 了适配器层的命令注册表（当时位于 `app.commands.handler`）；
    2. `chat_once()` 号称"Web 端可直接用"，实际 Web 从未使用（假共用 API）。

现在命令处理通过 `CommandDispatcher` 协议**注入**，本模块不再知道命令层的存在。
"""

from typing import Callable, Protocol

from app.core.agent import Agent


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


class CommandDispatcher(Protocol):
    """斜杠命令分派器。

    实现方（当前为 `app.interfaces.commands.registry.CommandHandler`）负责解析与执行，
    返回结构化结果；渲染由 UI 负责。本模块只关心"是否已被处理"，
    从而与命令层、渲染方式双双解耦。
    """

    def handle(self, user_input: str):
        """返回命令结果；返回 None 表示该输入不是命令，应交给 LLM。

        返回类型为 `app.interfaces.commands.result.CommandResult | None`，此处不标注具体类型
        以避免 services 依赖 commands（R2b）。
        """
        ...


class SessionRunner:
    """驱动 Agent 对话循环，与 UI 实现解耦。

    CLI 用法::

        runner = create_runner(config, approval_callback=cli_approval_callback)
        runner.run(DesktopPetUI(console))

    Web 端不应使用本类的 `run()`；进程级 Agent 生命周期由
    `app.services.agent_runtime.AgentRuntime` 负责。
    """

    def __init__(
        self,
        agent_factory: Callable[[], Agent],
        dispatcher_factory: Callable[[Agent], CommandDispatcher] | None = None,
        on_command_result: Callable[[object], None] | None = None,
    ):
        self._agent_factory = agent_factory
        self._dispatcher_factory = dispatcher_factory
        self._on_command_result = on_command_result
        self._agent: Agent | None = None
        self._dispatcher: CommandDispatcher | None = None

    @property
    def agent(self) -> Agent:
        assert self._agent is not None, "Agent 尚未初始化，请先调用 init()"
        return self._agent

    def init(self) -> None:
        """初始化 Agent 与命令分派器。"""
        self._agent = self._agent_factory()
        if self._dispatcher_factory is not None:
            self._dispatcher = self._dispatcher_factory(self._agent)

    def shutdown(self) -> str:
        """保存记忆并关闭 Agent。返回记忆保存结果字符串。"""
        assert self._agent is not None
        try:
            result = self._agent.remember_now()
        except Exception as error:  # 保存失败也要释放资源
            self._agent.shutdown()
            return f"记忆保存失败: {error}"
        self._agent.shutdown()
        return result

    def handle_command(self, user_input: str) -> bool:
        """尝试处理命令并渲染结果；返回 True 表示已处理。未配置分派器时恒为 False。"""
        if self._dispatcher is None:
            return False
        result = self._dispatcher.handle(user_input)
        if result is None:
            return False
        if self._on_command_result is not None:
            self._on_command_result(result)
        return True

    def chat_once(self, user_input: str):
        """单次流式对话：yield chunk，不含命令处理和记忆保存。"""
        assert self._agent is not None
        yield from self._agent.stream_chat(user_input=user_input)

    def run(self, ui: SessionUI) -> None:
        """启动 CLI 对话循环（阻塞）。"""
        self.init()
        assert self._agent is not None

        ui.on_start(self._agent)

        while True:
            user_input = input("\nYou: ")
            if user_input.lower() in ("exit", "quit"):
                result = self.shutdown()
                print(f"\n{result or '记忆已保存.'}")
                break

            if self.handle_command(user_input):
                # 命令执行结果已由 on_command_result 渲染；UI 只需刷新自身视图。
                # 若 UI 未实现该钩子，则退回重绘欢迎界面（历史行为）。
                on_command_result = getattr(ui, "on_command_result", None)
                if on_command_result is not None:
                    on_command_result(self._agent)
                else:
                    ui.on_start(self._agent)
                continue

            ui.on_before_reply(self._agent, user_input)
            full_response = ""
            for chunk in self._agent.stream_chat(user_input=user_input):
                full_response += chunk
                ui.on_chunk(self._agent, chunk)
            ui.on_after_reply(self._agent, full_response)


def create_runner(
    config,
    dispatcher_factory: Callable[[Agent], CommandDispatcher],
    approval_callback=None,
    on_command_result: Callable[[object], None] | None = None,
) -> SessionRunner:
    """构造 SessionRunner。

    `dispatcher_factory` 必须由调用方提供（CLI 传 `app.interfaces.cli.session.runner_factory`）：
    命令层属于适配器层，service 不得 import 它（依赖纪律 R2b），
    故这里不做默认装配。
    `on_command_result` 同样由调用方注入（CLI 传 rich 渲染函数）。
    """
    return SessionRunner(
        agent_factory=lambda: Agent(config, approval_callback=approval_callback),
        dispatcher_factory=dispatcher_factory,
        on_command_result=on_command_result,
    )
