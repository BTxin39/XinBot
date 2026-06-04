from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class MemoryProfile:
    user_name: str | None = None
    user_preferences: dict[str, str] = field(default_factory=dict)
    key_facts: list[str] = field(default_factory=list)
    relationship_stage: str = "new"
    conversation_summary: str = ""
    last_updated: str = ""

    @classmethod
    def empty(cls) -> "MemoryProfile":
        return cls()

    @classmethod
    def from_dict(cls, data: dict | None) -> "MemoryProfile":
        if not data:
            return cls.empty()
        return cls(
            user_name=data.get("user_name"),
            user_preferences=data.get("user_preferences", {}),
            key_facts=data.get("key_facts", []),
            relationship_stage=data.get("relationship_stage", "new"),
            conversation_summary=data.get("conversation_summary", ""),
            last_updated=data.get("last_updated", ""),
        )

    def to_dict(self) -> dict:
        return {
            "user_name": self.user_name,
            "user_preferences": self.user_preferences,
            "key_facts": self.key_facts,
            "relationship_stage": self.relationship_stage,
            "conversation_summary": self.conversation_summary,
            "last_updated": self.last_updated,
        }

    def to_prompt_text(self) -> str:
        parts: list[str] = []
        if self.user_name:
            parts.append(f"- 用户名叫 {self.user_name}")
        if self.user_preferences:
            prefs = ", ".join(
                f"{k}: {v}" for k, v in self.user_preferences.items()
            )
            parts.append(f"- 用户偏好：{prefs}")
        if self.key_facts:
            for fact in self.key_facts:
                parts.append(f"- {fact}")
        if self.relationship_stage and self.relationship_stage != "new":
            stage_map = {
                "familiar": "你和用户已经比较熟悉了",
                "close": "你和用户很亲近",
            }
            hint = stage_map.get(self.relationship_stage, "")
            if hint:
                parts.append(f"- {hint}")
        if self.conversation_summary:
            parts.append(f"- 上次对话摘要：{self.conversation_summary}")

        if not parts:
            return ""
        return "关于用户的信息：\n" + "\n".join(parts)

    def touch(self) -> None:
        self.last_updated = datetime.now().isoformat()
