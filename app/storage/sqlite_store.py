"""SQLite 消息存储引擎。

替代 JsonStorage，用 SQLite 实现增量写入和数据查询。
每条消息一行，只 INSERT 新增的不重写整个文件。

设计：
  - 单数据库文件，单表存所有 memory 的消息
  - memory_name 列区分不同的对话上下文
  - 复杂字段（tool_calls）存为 JSON 字符串
  - 自动建表，无需手动初始化
"""

import json
from datetime import datetime, timezone

from sqlalchemy import (
    Column,
    DateTime,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    create_engine,
    delete,
    insert,
    select,
)


class SQLiteStore:
    """SQLite 消息存储。

    使用方式：
        store = SQLiteStore("data/xinbot.db")
        store.insert_message("default", {"role":"user","content":"hi"})
        msgs = store.get_messages("default", limit=20)
        discarded = store.delete_oldest("default", keep=20)
    """

    def __init__(self, db_path: str = "data/xinbot.db"):
        self.engine = create_engine(
            f"sqlite:///{db_path}",
            connect_args={"check_same_thread": False},
            # SQLAlchemy echo for debugging
        )
        self.metadata = MetaData()

        # ── 消息表 ──────────────────────────────────────────────
        self._messages = Table(
            "messages",
            self.metadata,
            Column("id", Integer, primary_key=True, autoincrement=True),
            Column("memory_name", String(100), nullable=False, index=True),
            Column("role", String(20), nullable=False),
            Column("content", Text, nullable=True),
            Column("tool_calls", Text, nullable=True),         # JSON 字符串
            Column("tool_call_id", String(100), nullable=True),
            Column("reasoning_content", Text, nullable=True),
            Column("created_at", DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)),
        )

        # ── 元数据表 ────────────────────────────────────────────
        self._metadata_table = Table(
            "memory_metadata",
            self.metadata,
            Column("memory_name", String(100), primary_key=True),
            Column("description", Text, nullable=True, default=""),
        )

        self._migrations = Table(
            "memory_migrations", self.metadata,
            Column("memory_name", String(100), primary_key=True),
        )
        self.metadata.create_all(self.engine)

    # ── 消息操作 ───────────────────────────────────────────────

    def insert_message(self, memory_name: str, msg: dict):
        """插入一条消息。

        Args:
            memory_name: 对话上下文名（如 "default"）
            msg: {"role":"user","content":"hi",...}
                 可含 tool_calls, tool_call_id, reasoning_content
        """
        with self.engine.begin() as conn:
            conn.execute(
                insert(self._messages).values(
                    memory_name=memory_name,
                    role=msg.get("role", "?"),
                    content=msg.get("content"),
                    tool_calls=json.dumps(msg["tool_calls"], ensure_ascii=False)
                    if msg.get("tool_calls")
                    else None,
                    tool_call_id=msg.get("tool_call_id"),
                    reasoning_content=msg.get("reasoning_content"),
                )
            )

    def get_messages(self, memory_name: str, limit: int | None = None) -> list[dict]:
        """获取消息列表，按时间正序。

        Args:
            memory_name: 对话上下文名
            limit: 最多返回多少条。None 返回全部。

        Returns:
            [{"role":"user","content":"hi",...}, ...]
        """
        stmt = (
            select(self._messages)
            .where(self._messages.c.memory_name == memory_name)
            .order_by(self._messages.c.id.asc())
        )
        if limit is not None:
            stmt = stmt.order_by(None).order_by(self._messages.c.id.desc()).limit(limit)

        with self.engine.connect() as conn:
            rows = conn.execute(stmt).fetchall()
            return [_row_to_dict(row) for row in (reversed(rows) if limit is not None else rows)]

    def delete_oldest(self, memory_name: str, keep: int) -> list[dict]:
        """删除最旧的消息，保留最近 keep 条。

        Args:
            memory_name: 对话上下文名
            keep: 保留的消息数量

        Returns:
            被删除的消息列表（给 Summarizer 用）
        """
        with self.engine.begin() as conn:
            # 1. 查询要被删除的行（第 keep 条之前的所有行）
            subq = (
                select(self._messages.c.id)
                .where(self._messages.c.memory_name == memory_name)
                .order_by(self._messages.c.id.desc())
                .limit(keep)
            ).scalar_subquery()

            old_stmt = (
                select(self._messages)
                .where(
                    self._messages.c.memory_name == memory_name,
                    self._messages.c.id.not_in(subq),
                )
                .order_by(self._messages.c.id.asc())
            )
            old_rows = conn.execute(old_stmt).fetchall()
            discarded = [_row_to_dict(row) for row in old_rows]

            if discarded:
                ids_to_delete = [row.id for row in old_rows]
                conn.execute(
                    delete(self._messages).where(self._messages.c.id.in_(ids_to_delete))
                )

            return discarded

    def clear_messages(self, memory_name: str):
        """清空指定 memory 的所有消息。"""
        with self.engine.begin() as conn:
            conn.execute(
                delete(self._messages).where(
                    self._messages.c.memory_name == memory_name
                )
            )

    # ── 内存管理 ───────────────────────────────────────────────

    def get_memory_list(self) -> list[str]:
        """返回所有已有的 memory 名称。"""
        with self.engine.connect() as conn:
            rows = conn.execute(
                select(self._messages.c.memory_name).distinct()
            ).fetchall()
            metadata = conn.execute(select(self._metadata_table.c.memory_name)).fetchall()
            return sorted({row[0] for row in [*rows, *metadata]})

    def replace_messages(self, memory_name: str, messages: list[dict]):
        with self.engine.begin() as conn:
            conn.execute(delete(self._messages).where(self._messages.c.memory_name == memory_name))
            if messages:
                conn.execute(insert(self._messages), [dict(memory_name=memory_name, **message) for message in messages])

    def mark_migrated(self, memory_name: str):
        with self.engine.begin() as conn:
            if not conn.execute(select(self._migrations).where(self._migrations.c.memory_name == memory_name)).first():
                conn.execute(insert(self._migrations).values(memory_name=memory_name))

    def delete_memory(self, memory_name: str):
        self.mark_migrated(memory_name)
        with self.engine.begin() as conn:
            conn.execute(delete(self._messages).where(self._messages.c.memory_name == memory_name))
            conn.execute(delete(self._metadata_table).where(self._metadata_table.c.memory_name == memory_name))

    def get_message_count(self, memory_name: str) -> int:
        """返回指定 memory 的消息数量。"""
        stmt = (
            select(self._messages.c.id)
            .where(self._messages.c.memory_name == memory_name)
        )
        with self.engine.connect() as conn:
            return conn.execute(stmt).fetchall().__len__()

    # ── 元数据 ─────────────────────────────────────────────────

    def get_description(self, memory_name: str) -> str:
        stmt = select(self._metadata_table.c.description).where(
            self._metadata_table.c.memory_name == memory_name
        )
        with self.engine.connect() as conn:
            row = conn.execute(stmt).first()
            return row[0] if row else ""

    def set_description(self, memory_name: str, description: str):
        with self.engine.begin() as conn:
            # UPSERT: insert or replace
            existing = conn.execute(
                select(self._metadata_table).where(
                    self._metadata_table.c.memory_name == memory_name
                )
            ).first()
            if existing:
                conn.execute(
                    self._metadata_table.update()
                    .where(self._metadata_table.c.memory_name == memory_name)
                    .values(description=description)
                )
            else:
                conn.execute(
                    insert(self._metadata_table).values(
                        memory_name=memory_name, description=description
                    )
                )

    # ── 数据迁移 ───────────────────────────────────────────────

    def migrate_from_json(self, json_dir: str = "data/memory_json"):
        """从旧的 JSON 文件迁移数据到 SQLite。

        只在首次启动时检查。迁移后不删除旧文件（用户自己决定）。
        """
        import os
        from pathlib import Path

        json_path = Path(json_dir)
        if not json_path.exists():
            return

        migrated_count = 0
        for file in json_path.glob("*_memory.json"):
            memory_name = file.stem.replace("_memory", "")
            with self.engine.connect() as conn:
                if conn.execute(select(self._migrations).where(self._migrations.c.memory_name == memory_name)).first():
                    continue
            try:
                data = json.loads(file.read_text(encoding="utf-8"))
                messages = data if isinstance(data, list) else data.get("messages", [])

                # 检查 SQLite 里是否已有此 memory，有则跳过
                existing = self.get_message_count(memory_name)
                if existing > 0:
                    self.mark_migrated(memory_name)
                    continue

                # 导入
                for msg in messages:
                    self.insert_message(memory_name, msg)

                # 导入 description
                if isinstance(data, dict) and data.get("description"):
                    self.set_description(memory_name, data["description"])

                migrated_count += 1
                self.mark_migrated(memory_name)
            except (json.JSONDecodeError, OSError):
                pass

        if migrated_count > 0:
            import sys
            print(
                f"[SQLiteStore] 已从 JSON 文件迁移 {migrated_count} 个 memory",
                file=sys.stderr,
            )


# ── 辅助 ────────────────────────────────────────────────────────

def _row_to_dict(row) -> dict:
    """将 SQLAlchemy Row 转为消息 dict（兼容 OpenAI 格式）。"""
    msg: dict = {
        "role": row.role,
        "content": row.content,
    }
    # 只添加非空字段
    if row.tool_calls:
        try:
            msg["tool_calls"] = json.loads(row.tool_calls)
        except json.JSONDecodeError:
            pass
    if row.tool_call_id:
        msg["tool_call_id"] = row.tool_call_id
    if row.reasoning_content:
        msg["reasoning_content"] = row.reasoning_content
    return msg
