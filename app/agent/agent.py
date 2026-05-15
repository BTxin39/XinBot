from pathlib import Path

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

class Agent:

    def __init__(self):
        self.llm = LLMClient()
        self.memory = ChatMemory()
        self.state = AgentState()
        self.config = RuntimeConfig
        self.event_bus = EventBus()
        self.event_bus.subscribe(
            EmotionChangedEvent,
            on_emotion_changed
        )
        # self.system_prompt = self._load_system_prompt()
        # self.memory.add_message(
        #     role="system",
        #     content=self.system_prompt
        # )

    # DEPRECATED:
    def _load_system_prompt(self) -> str:
        prompt_path = Path(
            "app/llm/prompts/system.txt"
        )
        return prompt_path.read_text(
            encoding="utf-8"
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
    
    # DEPRECATED
    def chat(self, user_input: str) -> str:
        self.memory.add_message(
            role="user",
            content=user_input,
        )
        response = self.llm.chat(
            messages=self.memory.get_message(),
            model=self.config.MODEL_NAME,
            temperature=self.config.TEMPERATURE
        ) 
        self.memory.add_message(
            role="assistant",
            content=response
        )
        return response
    
    def stream_chat(self, user_input: str):
        # 根据能量值调整情绪
        # self._adjust_emotion_by_energy()
        
        # 先将用户输入添加到内存
        self.memory.add_message(
            role="user",
            content=user_input,
        )
        
        # messages = self.memory.get_message()
        messages = self._build_messages()  # 添加括号，正确调用方法
        full_response = ""

        for chunk in self.llm.stream_chat(
            messages=messages,
            model=self.config.MODEL_NAME,
            temperature=self.config.TEMPERATURE
        ):  # 调用LLM客户端的stream_chat方法
            full_response += chunk
            yield chunk

        # 当流式传输完成后，将完整的响应添加到内存
        self.memory.add_message(
            role="assistant",
            content=full_response
        )

    def get_status(self) -> AgentStatus:
        return AgentStatus(
            emotion=self.state.emotion,
            model_name=self.config.MODEL_NAME,
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
    
    # def _adjust_emotion_by_energy(self):
    #     """
    #     根据能量值调整情绪
    #     energy: 0-100
    #     """
    #     if self.state.energy < 20:
    #         self.state.emotion = "sleepy"  # 能量低时困倦
    #     elif self.state.energy > 80:
    #         self.state.emotion = "happy"  # 能量高时开心
    #     elif self.state.energy < 50:
    #         self.state.emotion = "sad"  # 能量较低时难过
    #     else:
    #         self.state.emotion = "normal"  # 其他情况下情绪正常