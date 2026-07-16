"""System Prompt 组装器 —— 从 PersonaStore 读取数据，分层拼接 prompt。"""

from app.core.state import AgentState
from app.core.persona import Persona, PersonaStore
from app.memory.profile import MemoryProfile


class PromptBuilder:
    """纯函数式组装：Persona + Profile + Emotion + Tools → System Prompt。"""

    @staticmethod
    def build(
        state: AgentState,
        profile: MemoryProfile | None = None,
        persona: Persona | None = None,
    ) -> str:
        """分层组装 System Prompt。"""
        store = PersonaStore.get()

        if persona is None:
            persona = store.get_persona("xin") or Persona(name="xin", display_name="xin")

        layers: list[str] = []

        # Layer 1: Persona
        layers.append(persona.to_prompt_text())

        # Layer 2: User Profile
        if profile:
            profile_text = profile.to_prompt_text()
            if profile_text:
                layers.append(profile_text)

        # Layer 3: Emotion
        emotion = store.get_emotion(state.emotion)
        if emotion:
            layers.append(
                f"当前状态：{emotion.description}。{emotion.behavior_modifier}"
            )

        # Layer 4: Tool Guidelines
        layers.append(
            "你可以使用工具来获取时间、查看状态或调整情绪。"
            "当用户询问时间或日期时，请使用 get_time 工具。"
            "当用户要求改变你的情绪时，请使用 set_emotion 工具。"
            "不需要告诉用户你正在使用工具，直接使用即可。"
        )

        return "\n\n".join(layers)
