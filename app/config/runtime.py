import json
from dataclasses import asdict, dataclass, field
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
    # RAG 配置
    embedding_model: str = "text-embedding-3-small"
    knowledge_dir: str = "data/knowledge"
    web_search_enabled: bool = False
    web_search_api_key: str = ""
    # MCP Server 配置列表。每个元素是 {"command": "...", "args": [...]}
    # 例如: {"command": "python", "args": ["scripts/mock_mcp_server.py"]}
    mcp_servers: list[dict] = field(default_factory=list)
    # SQLite 数据库路径，用于存储消息记忆（默认 data/xinbot.db）
    db_path: str = "data/xinbot.db"

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
            embedding_model=data.get("embedding_model", config.embedding_model),
            knowledge_dir=data.get("knowledge_dir", config.knowledge_dir),
            web_search_enabled=data.get("web_search_enabled", config.web_search_enabled),
            web_search_api_key=data.get("web_search_api_key", config.web_search_api_key),
            mcp_servers=data.get("mcp_servers", config.mcp_servers),
            db_path=data.get("db_path", config.db_path),
        )

    def save(self) -> None:
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(asdict(self), f, ensure_ascii=False, indent=2)

