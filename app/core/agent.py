from app.core.state import AgentState
from app.core.schemas import AgentStatus
from app.core.persona import Persona, PERSONAS
from app.core.tools.registry import ToolRegistry
from app.core.tools.manager import ToolManager
from app.core.tools.builtin.system import GetTimeTool, SetEmotionTool, GetStatusTool
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
        self.persona = PERSONAS.get(self.config.persona_name, PERSONAS["xin"])
        self.state = AgentState()
        self.event_bus = EventBus()
        self.event_bus.subscribe(EmotionChangedEvent, on_emotion_changed)

        self.tool_registry = ToolRegistry()
        self._register_builtin_tools()
        self.tool_manager = ToolManager(self.tool_registry)

    def _register_builtin_tools(self) -> None:
        self.tool_registry.register(GetTimeTool())
        self.tool_registry.register(SetEmotionTool(self))
        self.tool_registry.register(GetStatusTool(self))

    def _build_messages(self) -> list[dict]:
        system_prompt = PromptBuilder.build(
            self.state, self.memory.get_profile(), self.persona
        )
        messages = [{"role": "system", "content": system_prompt}]
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
