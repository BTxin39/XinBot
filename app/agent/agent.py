from app.agent.state import AgentState
from app.llm.client import LLMClient
from app.memory.chat_memory import ChatMemory
from app.llm.prompts.prompt_builder import PromptBuilder
from app.config.runtime import RuntimeConfig
from app.agent.schemas import AgentStatus
from app.events.bus import EventBus
from app.events.events import (
    EmotionChangedEvent,
    MessageReceiveEvent
)
from app.events.listeners import (
    on_emotion_changed
)
from app.config.validation import validate_config

class Agent:

    def __init__(self, config: RuntimeConfig | None = None):
        self.config = config or RuntimeConfig.load()
        validate_config(self.config)
        self.llm = LLMClient(self.config)
        self.memory = ChatMemory(self.config)
        self.state = AgentState()
        self.event_bus = EventBus()
        self.event_bus.subscribe(
            EmotionChangedEvent,
            on_emotion_changed
        )

    def _build_messages(self):
        system_prompt = PromptBuilder.build(self.state)
        messages = [
            {
                "role": "system",
                "content": system_prompt,
            }
        ]
        messages.extend(self.memory.get_message())
        return messages

    def stream_chat(self, user_input: str):
        self._observe(user_input)

        self._think()

        full_response = ""
        for chunk in self._respond():
            full_response += chunk
            yield chunk

        self._remember(full_response)


    def _observe(self, user_input: str) -> None:
        """观察：将用户输入写入工作记忆。"""
        self.memory.add_message(role="user", content=user_input)

    def _think(self) -> None:
        """思考：构建消息上下文（系统提示词 + 历史），为 LLM 调用做准备。"""
        self._current_messages = self._build_messages()

    def _respond(self):
        """回复：调用 LLM 流式生成回复文本。"""
        yield from self.llm.stream_chat(
            messages=self._current_messages,
            model=self.config.model_name,
            temperature=self.config.temperature,
        )

    def _remember(self, full_response: str) -> None:
        """记忆：将完整回复写入长期记忆。"""
        self.memory.add_message(role="assistant", content=full_response)

    def get_status(self) -> AgentStatus:
        return AgentStatus(
            emotion=self.state.emotion,
            provider=self.config.provider,
            model_name=self.config.model_name,
            memory_messages=len(self.memory.get_message())
        )
    
    def change_emotion(self, new_emotion: str):
        old_emotion = self.state.emotion
        self.state.emotion = new_emotion
        self.event_bus.emit(
            EmotionChangedEvent(
                old_emotion=old_emotion,
                new_emotion=new_emotion
            )
        )
