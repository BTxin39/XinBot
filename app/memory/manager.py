import json
from pathlib import Path
import os

from app.config.runtime import RuntimeConfig
from app.llm.client import LLMClient
from app.memory.chat_memory import ChatMemory
from app.memory.profile import MemoryProfile
from app.memory.extractor import MemoryExtractor


class MemoryManager:
    def __init__(self, config: RuntimeConfig | None = None):
        self.config = config or RuntimeConfig.load()
        self._chat = ChatMemory(self.config)
        self._profile_path = self._build_profile_path()
        self.profile = self._load_profile()
        self._extractor = MemoryExtractor(LLMClient(self.config))

    # ── 工作记忆委托 ──────────────────────────────────────────

    def add_message(self, role, content=None, **kwargs):
        self._chat.add_message(role=role, content=content, **kwargs)

    def get_message(self) -> list[dict]:
        return self._chat.get_message()

    def clear(self):
        self._chat.clear()

    def get_memory_list(self) -> list[str]:
        return self._chat.get_memory_list()

    def switch_memory(self, memory_name: str):
        self._chat.switch_memory(memory_name)
        self._profile_path = self._build_profile_path()
        self.profile = self._load_profile()

    # ── 长期记忆 ──────────────────────────────────────────────

    def remember(self) -> MemoryProfile:
        messages = self._chat.get_message()
        self.profile = self._extractor.extract(self.profile, messages)
        self.profile.touch()
        self._save_profile()
        return self.profile

    def get_profile(self) -> MemoryProfile:
        return self.profile

    # ── 内部 ──────────────────────────────────────────────────

    def _build_profile_path(self) -> str:
        memory_name = self.config.current_memory_name
        return os.path.join(self._chat.base_path, f"{memory_name}_profile.json")

    def _load_profile(self) -> MemoryProfile:
        path = Path(self._profile_path)
        if not path.exists():
            return MemoryProfile.empty()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return MemoryProfile.from_dict(data)
        except (json.JSONDecodeError, OSError):
            return MemoryProfile.empty()

    def _save_profile(self) -> None:
        path = Path(self._profile_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(self.profile.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
