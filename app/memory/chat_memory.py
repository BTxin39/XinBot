"""聊天消息记忆（工作记忆）。

负责管理当前会话的对话历史，支持多 memory 切换。
底层存储从 JSON 文件升级为 SQLite —— 增量写入，带时间戳。
"""

from app.memory.base import BaseMemory
from app.config.runtime import RuntimeConfig
from app.storage.sqlite_store import SQLiteStore


class ChatMemory(BaseMemory):
    def __init__(self, config: RuntimeConfig | None = None):
        self.config = config or RuntimeConfig.load()
        db_path = getattr(self.config, "db_path", "") or "data/xinbot.db"
        self._store = SQLiteStore(db_path)

        # 首次启动：从旧 JSON 文件迁移
        self._store.migrate_from_json()

        # 当前活跃的 memory
        self._current_memory_name = self.config.current_memory_name
        # 内存缓存：最近的消息
        self.messages: list[dict] = self._store.get_messages(
            self._current_memory_name,
            limit=self.config.max_memory_messages,
        )

    # ── 消息操作 ───────────────────────────────────────────────

    def add_message(self, role, content=None, **kwargs):
        """添加一条消息。

        写入流程：
        1. SQLite INSERT（持久化）
        2. 内存列表追加
        3. 裁剪溢出消息（SQLite + 内存同步）

        Returns:
            被裁剪丢弃的消息列表。
        """
        msg = {"role": role, "content": content, **kwargs}
        # 持久化：只 INSERT 一行
        self._store.insert_message(self._current_memory_name, msg)
        # 内存：追加
        self.messages.append(msg)
        # 裁剪
        discarded = self._trim_messages()
        return discarded

    def _trim_messages(self) -> list[dict]:
        """裁剪超出窗口的消息，SQLite 和内存同步删除。

        返回被丢弃的消息列表，交给调用方做摘要处理。
        """
        if len(self.messages) <= self.config.max_memory_messages:
            return []

        # SQLite 删除旧消息 + 返回被删内容（一次操作）
        discarded = self._store.delete_oldest(
            self._current_memory_name,
            keep=self.config.max_memory_messages,
        )
        # 内存同步裁剪
        cut = len(self.messages) - self.config.max_memory_messages
        self.messages = self.messages[cut:]
        return discarded

    def get_message(self) -> list[dict]:
        """返回当前内存中的所有消息。"""
        return self.messages

    def clear(self):
        """清空当前 memory 的所有消息（SQLite + 内存）。"""
        self._store.clear_messages(self._current_memory_name)
        self.messages.clear()

    # ── Memory 管理 ────────────────────────────────────────────

    def get_memory_list(self) -> list[str]:
        """返回所有已有的 memory 名称。"""
        names = self._store.get_memory_list()
        # 确保当前 memory 在列表中
        if self._current_memory_name not in names:
            names.append(self._current_memory_name)
        return names

    def switch_memory(self, memory_name: str):
        """切换到另一个 memory，从 SQLite 加载该 memory 的消息。"""
        self._current_memory_name = memory_name
        self.messages = self._store.get_messages(
            memory_name,
            limit=self.config.max_memory_messages,
        )

    def get_memory_description(self, memory_name: str) -> str:
        return self._store.get_description(memory_name)

    def set_memory_description(self, memory_name: str, description: str):
        self._store.set_description(memory_name, description)

    @property
    def base_path(self) -> str:
        """兼容旧代码（MemoryManager 用 base_path 拼接 profile 路径）。"""
        return "data/memory_json"
