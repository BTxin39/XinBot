"""Agent 生命周期（单例 / 重建 / 释放）—— 跨端唯一入口。

取代原先分散的实现（已删除的 `web/agent_manager.py` 与 `core/session.py` 的 `init()`），
见 docs/DECISIONS_V0.2.md §7。

职责边界：
    - 只做**生命周期**与对话驱动，不含 HTTP 语义、不 import fastapi
    - 审批回调由调用方在构造时注入；不传 = 按 ToolGuard fail-safe 拒绝危险工具
    - 配置/角色变更后的重建统一走 `rebuild()`（惰性），不再由各路由各自 shutdown

为什么用惰性 `rebuild()` 而不是立即释放：
    只有真正取用 Agent 时才重建。校验失败的请求不会白白销毁运行中的 Agent，
    也不会把重建时机散落到 8 个路由里。
"""

from threading import RLock

from app.config.runtime import RuntimeConfig
from app.core.agent import Agent
from app.core.tools.guard import ApprovalCallback


class AgentRuntime:
    """Agent 单例持有者；同时可作为独立实例使用（需自定义回调或做测试时）。"""

    _default: "AgentRuntime | None" = None

    # 类级 RLock：与旧 AgentManager.lock 用法兼容，供需要跨多步持锁的路由使用
    lock = RLock()

    def __init__(self, approval_callback: ApprovalCallback | None = None):
        self._approval_callback = approval_callback
        self._instance: Agent | None = None
        self._latest_message: str = ""

    # ── 单例入口（Web 等进程级共享场景） ──────────────────────

    @classmethod
    def default(cls) -> "AgentRuntime":
        """进程级默认实例：不注入审批回调 → 危险工具默认拒绝。"""
        if cls._default is None:
            cls._default = cls()
        return cls._default

    @classmethod
    def get(cls) -> Agent:
        return cls.default().agent()

    @classmethod
    def instance(cls) -> Agent | None:
        """已构造的 Agent；尚未懒加载时返回 None（供状态查询等只读场景）。"""
        return cls.default().current()

    @classmethod
    def rebuild(cls) -> None:
        """标记重建：下次 get() 时以最新配置重新构造 Agent。"""
        cls.default().invalidate()

    @classmethod
    def shutdown(cls) -> None:
        """立即释放当前 Agent（应用退出、或需要确定性释放时使用）。"""
        cls.default().release()

    @classmethod
    def latest_message(cls) -> str:
        return cls.default()._latest_message

    @classmethod
    def set_latest_message(cls, message: str) -> None:
        cls.default()._latest_message = message

    @classmethod
    def chat(cls, user_input: str, **options) -> str:
        return cls.default().send(user_input, **options)

    @classmethod
    def reset_for_tests(cls) -> None:
        """测试专用：释放实例并清除类级默认持有者。"""
        instance = cls._default
        if instance is not None:
            instance.release()
        cls._default = None

    # ── 实例 API ─────────────────────────────────────────────

    def current(self) -> Agent | None:
        return self._instance

    def agent(self) -> Agent:
        """惰性构造 Agent，并在空记忆时灌入角色首条问候语。"""
        if self._instance is None:
            # 不传 approval_callback 时 ToolGuard 按 fail-safe 拒绝危险工具
            agent = Agent(RuntimeConfig.load(), approval_callback=self._approval_callback)
            self._inject_greeting(agent)
            self._instance = agent
        return self._instance

    def invalidate(self) -> None:
        """释放当前实例并清空，下次 agent() 以最新配置重建。

        释放（而非单纯丢弃引用）是必要的：Agent 持有 MCP 子进程，
        只丢引用会让子进程泄漏。
        """
        if self._instance is not None:
            self._instance.shutdown()
        self._instance = None
        self._latest_message = ""

    def release(self) -> None:
        """立即释放实例（应用退出时使用）。"""
        self.invalidate()

    def send(self, user_input: str, **options) -> str:
        """一次完整对话，返回完整回复并记录 latest_message。"""
        parts = list(self.agent().stream_chat(user_input, **options))
        reply = "".join(parts)
        self._latest_message = reply
        return reply

    def stream(self, user_input: str, **options):
        """流式对话：逐块 yield，结束时记录 latest_message。"""
        collected: list[str] = []
        for chunk in self.agent().stream_chat(user_input, **options):
            collected.append(chunk)
            yield chunk
        self._latest_message = "".join(collected)

    @classmethod
    def refresh_persona(cls, name: str) -> bool:
        """把已运行 Agent 的角色换成最新版本（角色被编辑后调用）。

        只有当运行中的 Agent 正使用该角色时才生效；未加载时返回 False，
        因为下次 `agent()` 会自然读到新角色。
        返回 True 表示确实热更新了运行实例。

        注意：这里必须是 **classmethod**。路由是以 `AgentRuntime.refresh_persona(name)`
        调用的；若写成实例方法，`name` 会被当成 `self`，抛
        "missing 1 required positional argument: 'name'"（v0.2.1 实际踩过）。
        """
        agent = cls.default().current()
        if agent is None or agent.config.persona_name != name:
            return False

        from app.core.persona import PersonaStore
        from app.core.tools.builtin.rag import SearchKnowledgeTool

        persona = PersonaStore.get().get_persona(name)
        if persona is None:
            return False

        agent.persona = persona
        # 知识库检索工具持有角色引用（用于 role tag 过滤），需同步替换
        tool = agent.tool_registry.get("search_knowledge")
        if isinstance(tool, SearchKnowledgeTool):
            tool.persona = persona
        return True

    # ── 内部 ────────────────────────────────────────────────

    @staticmethod
    def _inject_greeting(agent: Agent) -> None:
        """空记忆时写入角色卡的 first_mes（原实现分散在 session 与 agent_manager 两处）。"""
        persona = agent.persona
        if not persona or agent.memory.get_message():
            return
        greeting = persona.character_card.get("data", {}).get("first_mes", "")
        if greeting:
            agent.memory.add_message(
                role="assistant",
                content=persona.render_macros(greeting),
            )
