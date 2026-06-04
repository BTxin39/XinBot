import json
from dataclasses import asdict, dataclass
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

CONFIG_PATH = Path("data/runtime_config.json")

@dataclass
class RuntimeConfig:
    model_name: str = (
        os.getenv("XINBOT_MODEL")
        or "deepseek-v4-flash"
    )
    temperature: float = 0.7
    max_memory_messages: int = 20
    provider: str = (
        os.getenv("XINBOT_PROVIDER")
        or "deepseek"
    )
    current_memory_name: str = "default"
    persona_name: str = "xin"

    @classmethod
    def load(cls) -> "RuntimeConfig":
        config = cls()
        if not CONFIG_PATH.exists():
            return config

        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            data: dict = json.load(f)

        return cls(
            model_name=data.get("model_name", config.model_name),
            temperature=data.get("temperature", config.temperature),
            max_memory_messages=data.get(
                "max_memory_messages",
                config.max_memory_messages,
            ),
            provider=data.get("provider", config.provider),
            current_memory_name=data.get(
                "current_memory_name",
                config.current_memory_name,
            ),
            persona_name=data.get("persona_name", config.persona_name),
        )

    def save(self) -> None:
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(asdict(self), f, ensure_ascii=False, indent=2)
