"""Persona 数据层 —— 从 data/personas.json 加载角色和情绪定义。

统一管理 Persona 和 Emotion，格式简洁，便于后续 Web 端读写。
"""

from dataclasses import dataclass, field
from pathlib import Path
import json


PERSONAS_PATH = Path("data/personas.json")


# ── Data Models ────────────────────────────────────────────────

@dataclass
class Persona:
    name: str
    display_name: str
    traits: list[str] = field(default_factory=list)
    speaking_style: str = ""
    background: str = ""
    constraints: list[str] = field(default_factory=list)
    builtin: bool = False
    character_card: dict = field(default_factory=dict)
    pet_model: str = ""
    avatar: str = ""

    def to_prompt_text(self) -> str:
        lines = [f"你是 {self.display_name}。", self.background, ""]

        if self.traits:
            lines.append(f"性格特征：{'、'.join(self.traits)}。")

        if self.speaking_style:
            lines.append(f"说话风格：{self.speaking_style}")

        if self.constraints:
            lines.append("行为约束：")
            for c in self.constraints:
                lines.append(f"- {c}")

        card = self.character_card.get("data", {})
        for key, label in (("description", "角色描述"), ("personality", "性格"),
                           ("scenario", "场景"), ("mes_example", "对话示例"),
                           ("system_prompt", "角色指令")):
            if card.get(key):
                lines.append(f"{label}: {card[key]}")
        return self.render_macros("\n".join(lines))

    def render_macros(self, text: str) -> str:
        return text.replace("{{char}}", self.display_name).replace("{{user}}", "用户")

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "display_name": self.display_name,
            "traits": self.traits,
            "speaking_style": self.speaking_style,
            "background": self.background,
            "constraints": self.constraints,
            "builtin": self.builtin,
            "character_card": self.character_card,
            "pet_model": self.pet_model,
            "avatar": self.avatar,
        }


@dataclass
class Emotion:
    name: str
    description: str
    behavior_modifier: str


# ── Store ──────────────────────────────────────────────────────

class PersonaStore:
    """Persona 和 Emotion 的 JSON 文件存储。

    单例模式，首次访问时加载，之后从缓存返回。
    用户自定义的 persona 和内置的一样存在同一个 JSON 文件中。
    """

    _instance: "PersonaStore | None" = None

    def __init__(self):
        if not PERSONAS_PATH.exists():
            self._init_default()
        else:
            self._load()

    @classmethod
    def get(cls) -> "PersonaStore":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reload(cls) -> "PersonaStore":
        """强制重新加载（用于 CLI 修改后刷新）。"""
        cls._instance = cls()
        return cls._instance

    def _init_default(self):
        """第一次运行时用内置默认值创建文件。"""
        self.personas: dict[str, Persona] = {}
        self.emotions: dict[str, Emotion] = {}
        self._save()

    def _load(self):
        data = json.loads(PERSONAS_PATH.read_text(encoding="utf-8"))

        self.personas = {}
        for name, p in data.get("personas", {}).items():
            self.personas[name] = Persona(
                name=p["name"],
                display_name=p.get("display_name", name),
                traits=p.get("traits", []),
                speaking_style=p.get("speaking_style", ""),
                background=p.get("background", ""),
                constraints=p.get("constraints", []),
                builtin=p.get("builtin", False),
                character_card=p.get("character_card", {}),
                pet_model=p.get("pet_model", ""),
                avatar=p.get("avatar", ""),
            )

        self.emotions = {}
        for name, e in data.get("emotions", {}).items():
            self.emotions[name] = Emotion(
                name=e["name"],
                description=e["description"],
                behavior_modifier=e["behavior_modifier"],
            )

    def _save(self):
        data = {
            "personas": {n: p.to_dict() for n, p in self.personas.items()},
            "emotions": {
                n: {"name": e.name, "description": e.description, "behavior_modifier": e.behavior_modifier}
                for n, e in self.emotions.items()
            },
        }
        PERSONAS_PATH.parent.mkdir(parents=True, exist_ok=True)
        PERSONAS_PATH.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    # ── Persona CRUD ───────────────────────────────────────

    def get_persona(self, name: str) -> Persona | None:
        return self.personas.get(name)

    def list_personas(self) -> list[Persona]:
        return list(self.personas.values())

    def add_persona(self, persona: Persona) -> None:
        if persona.name in self.personas:
            raise ValueError(f"Persona '{persona.name}' 已存在。")
        self.personas[persona.name] = persona
        self._save()

    def update_persona(self, name: str, updates: dict) -> None:
        p = self.personas.get(name)
        if p is None:
            raise ValueError(f"Persona '{name}' 不存在。")
        for key, value in updates.items():
            if hasattr(p, key):
                setattr(p, key, value)
        self._save()

    def remove_persona(self, name: str) -> None:
        p = self.personas.get(name)
        if p is None:
            raise ValueError(f"Persona '{name}' 不存在。")
        if p.builtin:
            raise ValueError(f"不能删除内置 Persona '{name}'。")
        del self.personas[name]
        self._save()

    # ── Emotion 查询 ───────────────────────────────────────

    def get_emotion(self, name: str) -> Emotion:
        return self.emotions.get(name, self.emotions.get("normal"))
