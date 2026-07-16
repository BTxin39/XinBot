from app.core.state import AgentState
from app.core.schemas import AgentStatus
from app.core.persona import Persona, PersonaStore
from app.core.tools.registry import ToolRegistry
from app.core.tools.manager import ToolManager
from app.core.tools.guard import ToolGuard, cli_approval_callback
from app.core.tools.builtin.system import GetTimeTool, SetEmotionTool, GetStatusTool
from app.core.tools.builtin.file_ops import ReadFileTool, ListDirectoryTool, WriteFileTool
from app.core.tools.mcp_client import MCPClient, MCPConnectionError
from app.core.tools.mcp_wrapper import MCPWrapperTool
from app.llm.client import LLMClient
from app.memory.manager import MemoryManager
from app.llm.prompts.prompt_builder import PromptBuilder
from app.config.runtime import RuntimeConfig
from app.config.validation import validate_config
from app.events.bus import EventBus
from app.events.events import EmotionChangedEvent
from app.events.listeners import on_emotion_changed

MAX_TOOL_ITERATIONS = 5


class Agent:

    def __init__(self, config: RuntimeConfig | None = None):
        self.config = config or RuntimeConfig.load()
        validate_config(self.config)
        self.llm = LLMClient(self.config)
        self.memory = MemoryManager(self.config)
        self.persona = PersonaStore.get().get_persona(self.config.persona_name) or PersonaStore.get().get_persona("xin")
        self.state = AgentState()
        self.event_bus = EventBus()
        self.event_bus.subscribe(EmotionChangedEvent, on_emotion_changed)

        self.tool_registry = ToolRegistry()
        self._mcp_clients: list[MCPClient] = []
        self._register_builtin_tools()
        self._register_mcp_tools()
        self.tool_manager = ToolManager(
            self.tool_registry,
            guard=ToolGuard(cli_approval_callback),
        )

    def _register_builtin_tools(self) -> None:
        self.tool_registry.register(GetTimeTool())
        self.tool_registry.register(SetEmotionTool(self))
        self.tool_registry.register(GetStatusTool(self))
        self.tool_registry.register(ReadFileTool())
        self.tool_registry.register(ListDirectoryTool())
        self.tool_registry.register(WriteFileTool())

    def _register_mcp_tools(self) -> None:
        """从配置的 MCP Server 发现并注册远端工具。

        每个 MCP Server 作为独立子进程启动，通过 JSON-RPC 通信。
        一个 Server 启动失败不影响其他 Server，也不影响 Agent 启动。
        """
        for server_config in self.config.mcp_servers:
            command_list = [server_config["command"]] + server_config.get("args", [])
            try:
                client = MCPClient(command_list)
                client.initialize()
                tools = client.list_tools()
            except MCPConnectionError as e:
                # 一个 Server 挂了不影响 Agent 整体
                import sys
                print(
                    f"\n[MCP] 无法连接 MCP Server '{server_config['command']}': {e}",
                    file=sys.stderr,
                )
                continue

            self._mcp_clients.append(client)
            for tool_def in tools:
                wrapper = MCPWrapperTool(tool_def, client)
                self.tool_registry.register(wrapper)
                import sys
                print(
                    f"\n[MCP] 已注册远端工具: {tool_def.name} "
                    f"(来自 {' '.join(command_list)})",
                    file=sys.stderr,
                )

    def shutdown(self):
        """关闭所有 MCP 子进程，释放资源。

        应在退出对话循环前调用。
        """
        for client in self._mcp_clients:
            client.close()
        self._mcp_clients.clear()

    def _build_messages(self) -> list[dict]:
        system_prompt = PromptBuilder.build(
            self.state, self.memory.get_profile(), self.persona
        )
        messages = [{"role": "system", "content": system_prompt}]

        # 运行摘要：当对话超出窗口时，旧消息会被压缩成摘要注入
        summary = self.memory.get_summary()
        if summary:
            messages.append({
                "role": "system",
                "content": f"[近期对话摘要]\n{summary}",
            })

        messages.extend(self.memory.get_message())
        return messages

    def stream_chat(self, user_input: str):
        self._observe(user_input)

        iterations = 0
        while iterations < MAX_TOOL_ITERATIONS:
            iterations += 1
            messages = self._build_messages()
            response = self.llm.chat(
                messages=messages,
                tools=self.tool_registry.get_tools_schema(),
            )

            if response.tool_calls:
                extra: dict = {"tool_calls": response.tool_calls}
                # DeepSeek thinking 模型要求回传 reasoning_content
                if response.reasoning_content is not None:
                    extra["reasoning_content"] = response.reasoning_content
                self.memory.add_message(
                    role="assistant",
                    content=response.content,
                    **extra,
                )
                tool_results = self.tool_manager.execute(response.tool_calls)
                for tr in tool_results:
                    self.memory.add_message(**tr)
                continue

            full_response = response.content or ""
            self._remember(full_response)
            yield full_response
            return

        yield "（已达到最大工具调用次数，请重新输入。）"

    def _observe(self, user_input: str) -> None:
        self.memory.add_message(role="user", content=user_input)

    def _remember(self, full_response: str) -> None:
        self.memory.add_message(role="assistant", content=full_response)

    def get_status(self) -> AgentStatus:
        return AgentStatus(
            emotion=self.state.emotion,
            provider=self.config.provider,
            model_name=self.config.model_name,
            memory_messages=len(self.memory.get_message()),
        )

    def remember_now(self) -> str:
        profile = self.memory.remember()
        parts: list[str] = []

        if profile.user_name:
            parts.append(f"名字: {profile.user_name}")
        if profile.key_facts:
            parts.append(f"{len(profile.key_facts)} 个关键事实")
        if profile.user_preferences:
            prefs = ", ".join(
                f"{k}={v}" for k, v in profile.user_preferences.items()
            )
            parts.append(f"偏好: {prefs}")
        if profile.conversation_summary:
            parts.append(f"对话摘要: {profile.conversation_summary}")
        if profile.relationship_stage and profile.relationship_stage != "new":
            stage_names = {"familiar": "熟悉", "close": "亲近"}
            parts.append(
                f"关系: {stage_names.get(profile.relationship_stage, profile.relationship_stage)}"
            )

        if parts:
            return "记忆已保存 ✓\n  " + "\n  ".join(parts)
        return "已分析对话内容，未发现新的长期信息。"

    def change_emotion(self, new_emotion: str):
        old_emotion = self.state.emotion
        self.state.emotion = new_emotion
        self.event_bus.emit(
            EmotionChangedEvent(
                old_emotion=old_emotion,
                new_emotion=new_emotion,
            )
        )

