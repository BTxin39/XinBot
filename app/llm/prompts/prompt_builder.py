from pathlib import Path

from app.core.state import AgentState, EMOTIONS
from app.core.persona import Persona, PERSONAS
from app.memory.profile import MemoryProfile


class PromptTemplate:

    def __init__(self):
        self.templates_dir = Path("app/llm/prompts/templates")
        self.templates_dir.mkdir(exist_ok=True)
        self._load_templates()

    def _load_templates(self):
        self.base_prompts = {
            "system": self._read_template(
                "system.txt",
                "你是一只 AI 桌宠。你的名字叫 xin。你会温柔、简短地和用户聊天。",
            ),
        }

    def _read_template(self, filename: str, default_content: str) -> str:
        template_path = self.templates_dir / filename
        if not template_path.exists():
            template_path.write_text(default_content, encoding="utf-8")
        return template_path.read_text(encoding="utf-8")

    def get_template(self, name: str) -> str:
        if name in self.base_prompts:
            return self.base_prompts[name]
        return self._read_template(f"{name}.txt", f"Default {name} template")

    def update_template(self, name: str, content: str):
        template_path = self.templates_dir / f"{name}.txt"
        template_path.write_text(content, encoding="utf-8")
        self.base_prompts[name] = content


class PromptBuilder:

    @staticmethod
    def build(
        state: AgentState,
        profile: MemoryProfile | None = None,
        persona: Persona | None = None,
    ) -> str:
        """分层组装 System Prompt，按优先级从高到低排列。"""
        if persona is None:
            persona = PERSONAS["xin"]

        layers: list[str] = []

        # Layer 1: Persona — 角色身份（最重要）
        layers.append(persona.to_prompt_text())

        # Layer 2: User Profile — 用户信息
        if profile:
            profile_text = profile.to_prompt_text()
            if profile_text:
                layers.append(profile_text)

        # Layer 3: Emotion — 当前情绪
        emotion = EMOTIONS.get(state.emotion, EMOTIONS["normal"])
        layers.append(
            f"当前状态：{emotion.description}。{emotion.behavior_modifier}"
        )

        # Layer 4: Tool Guidelines — 工具使用说明
        layers.append(
            "你可以使用工具来获取时间、查看状态或调整情绪。"
            "当用户询问时间或日期时，请使用 get_time 工具。"
            "当用户要求改变你的情绪时，请使用 set_emotion 工具。"
            "不需要告诉用户你正在使用工具，直接使用即可。"
        )

        return "\n\n".join(layers)

    @staticmethod
    def build_system_prompt(
        state: AgentState,
        profile: MemoryProfile | None = None,
        persona: Persona | None = None,
    ) -> str:
        return PromptBuilder.build(state, profile, persona)
