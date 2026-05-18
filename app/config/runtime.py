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

    @property
    def MODEL_NAME(self) -> str:
        return self.model_name

    @property
    def TEMPERATURE(self) -> float:
        return self.temperature

    @property
    def MAX_MEMORY_MESSAGES(self) -> int:
        return self.max_memory_messages

    @property
    def PROVIDER(self) -> str:
        return self.provider

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
        )

    def save(self) -> None:
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(asdict(self), f, ensure_ascii=False, indent=2)
