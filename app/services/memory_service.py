"""记忆业务编排 —— 跨端唯一入口（docs/DECISIONS_V0.2.md §5.2、§7）。

解决的缺陷 **D4**：此前 CLI 经 `ChatMemory`、Web 直接开 `SQLiteStore`，
两边各自实现"列表 / 读取 / 建删 / 清空 / 激活"的编排与校验，容易漂移。
现在这些编排只在 service 里有一份，`interfaces/` 只做协议转换。

分层约束：
    - 本模块不得 import `fastapi` / `rich` / `typer`（R2）
    - 校验失败抛 `MemoryError` 类的领域异常（本模块的 `MemoryServiceError`），
      由适配器翻译成 `HTTPException` 或终端提示

关于**激活语义**（原 D1 的一半）：切换角色时应同时切换记忆上下文，
使各角色拥有独立对话历史。命名规则收敛在 `memory_name_for_persona()`，
CLI 与 Web 共用，不再各自实现。
"""

import json
import re
from pathlib import Path

from app.config.runtime import RuntimeConfig
from app.storage.sqlite_store import SQLiteStore

# 角色记忆名的历史前缀。
#
# ⚠️ 决策记录（docs/DECISIONS_V0.2.md §5.3 / Q1）：**保留 `web-` 前缀，不做改名迁移。**
# 理由：该前缀已在 docs/WEB_COMPANION.md 中作为对外承诺写明，改名需要改写用户
# data/xinbot.db 中的记忆键，属于不可逆操作；而"两端命名不一致"的真正危害
# （CLI 切角色不改记忆、两端各写一份命名规则）由本模块收敛即可消除。
# 若将来确要改名，应在此处加"读旧名兼容层"，而不是直接改常量。
PERSONA_MEMORY_PREFIX = "web-"

PROFILE_DIR = Path("data/memory_json")


class MemoryServiceError(Exception):
    """记忆操作的领域异常。适配器负责翻译成 HTTP 状态码或终端提示。"""

    def __init__(self, message: str, code: str = "invalid"):
        self.code = code
        super().__init__(message)


def memory_name_for_persona(persona_name: str) -> str:
    """角色 → 其专属记忆名（唯一实现，CLI / Web 共用）。"""
    return f"{PERSONA_MEMORY_PREFIX}{persona_name}"


def is_valid_memory_name(name: str) -> bool:
    """记忆名只允许字母、数字、下划线、连字符。"""
    return bool(re.fullmatch(r"[\w-]{1,100}", name))


class MemoryService:
    """记忆的查询与变更。**无缓存**：每次操作直接读写 SQLite，天然两端一致。"""

    def __init__(self, config: RuntimeConfig | None = None):
        self.config = config or RuntimeConfig.load()
        self.db_path = self.config.db_path or "data/xinbot.db"
        self.profile_dir = PROFILE_DIR

    # ── 与存储交互的低层封装 ──────────────────────────────────

    def _store(self):
        """打开一个 SQLiteStore（调用方负责关闭）。"""
        return SQLiteStore(self.db_path)

    def _profile_path(self, name: str) -> Path:
        return self.profile_dir / f"{self._require_valid(name)}_profile.json"

    def _require_valid(self, name: str) -> str:
        if not is_valid_memory_name(name):
            raise MemoryServiceError(
                "记忆名称只能包含字母、数字、下划线和连字符", code="invalid_name"
            )
        return name

    # ── 查询 ─────────────────────────────────────────────────

    def list_memories(self) -> list[dict]:
        """列出全部记忆（含当前激活项）。"""
        store = self._store()
        try:
            current = self.config.current_memory_name
            names = sorted(set(store.get_memory_list()) | {current})
            return [
                {
                    "name": name,
                    "description": store.get_description(name),
                    "count": store.get_message_count(name),
                    "active": name == current,
                }
                for name in names
            ]
        finally:
            store.engine.dispose()

    def get_memory(self, name: str) -> dict:
        """读取单个记忆的完整内容（消息 + 长期画像）。"""
        self._require_valid(name)
        store = self._store()
        try:
            self._require_exists(store, name)
            return {
                "name": name,
                "description": store.get_description(name),
                "messages": store.get_messages(name),
                "profile": self.read_profile(name),
            }
        finally:
            store.engine.dispose()

    def get_message_count(self, name: str) -> int:
        store = self._store()
        try:
            return store.get_message_count(name)
        finally:
            store.engine.dispose()

    # ── 长期画像（JSON 文件） ────────────────────────────────

    def read_profile(self, name: str) -> dict:
        path = self._profile_path(name)
        if not path.is_file():
            return {}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}

    def write_profile(self, name: str, profile: dict) -> None:
        path = self._profile_path(name)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def delete_profile(self, name: str) -> None:
        self._profile_path(name).unlink(missing_ok=True)

    # ── 变更 ─────────────────────────────────────────────────

    def create_memory(self, name: str, description: str = "") -> dict:
        self._require_valid(name)
        store = self._store()
        try:
            if name in store.get_memory_list() or name == self.config.current_memory_name:
                raise MemoryServiceError("记忆已存在", code="exists")
            store.set_description(name, description)
            # 标记已迁移，避免该名字被 JSON 遗留文件重新导入
            store.mark_migrated(name)
            return {"name": name}
        finally:
            store.engine.dispose()

    def update_memory(
        self,
        name: str,
        description: str | None = None,
        messages: list[dict] | None = None,
        profile: dict | None = None,
    ) -> dict:
        """整体更新记忆（描述 / 消息 / 画像，任选其一）。"""
        self._require_valid(name)
        store = self._store()
        try:
            self._require_exists(store, name)
            if description is not None:
                store.set_description(name, description)
            if messages is not None:
                store.replace_messages(name, messages)
            if profile is not None:
                self.write_profile(name, profile)
        finally:
            store.engine.dispose()
        return self.get_memory(name)

    def set_description(self, name: str, description: str) -> None:
        self._require_valid(name)
        store = self._store()
        try:
            self._require_exists(store, name)
            store.set_description(name, description)
        finally:
            store.engine.dispose()

    def clear_memory(self, name: str) -> dict:
        """清空消息，保留描述与画像。"""
        self._require_valid(name)
        store = self._store()
        try:
            self._require_exists(store, name)
            description = store.get_description(name)
            store.mark_migrated(name)
            store.clear_messages(name)
            # 保留描述：清空消息不应丢描述
            store.set_description(name, description)
            return {"cleared": name}
        finally:
            store.engine.dispose()

    def delete_memory(self, name: str) -> dict:
        self._require_valid(name)
        if name == self.config.current_memory_name:
            raise MemoryServiceError("请先切换到其他记忆", code="active")
        store = self._store()
        try:
            self._require_exists(store, name)
            store.delete_memory(name)
        finally:
            store.engine.dispose()
        self.delete_profile(name)
        return {"deleted": name}

    def activate_memory(self, name: str) -> str:
        """把某个记忆设为当前激活项。返回该名字。"""
        self._require_valid(name)
        store = self._store()
        try:
            self._require_exists(store, name)
        finally:
            store.engine.dispose()
        self._set_active(name)
        return name

    def activate_persona_memory(self, persona_name: str) -> str:
        """切换角色时切换到该角色的记忆。

        这是 **D1 的统一实现**：此前只有 Web 这么做（写 web-{name}），
        CLI 的 `persona set` 只改 persona_name，导致两端行为分叉。
        记忆可以尚不存在——首次对话时自然创建。
        """
        name = memory_name_for_persona(persona_name)
        self._set_active(name)
        return name

    # ── 内部 ─────────────────────────────────────────────────

    def _set_active(self, name: str) -> None:
        config = self.config
        config.current_memory_name = name
        config.save()
        # 让本进程内的 config 副本与磁盘一致
        self.config = config

    def _require_exists(self, store: SQLiteStore, name: str) -> None:
        """记忆必须已存在，或是当前激活项（允许空记忆被提前引用）。"""
        if name not in store.get_memory_list() and name != self.config.current_memory_name:
            raise MemoryServiceError("记忆不存在", code="missing")
