"""记忆管理 REST 接口 —— 只做协议转换，业务编排在 `app/services/memory_service.py`。

P3 变更（docs/DECISIONS/DECISIONS_V0.2.0.md §5.2）：
    本模块原先直接 `import SQLiteStore` 并自己实现"校验 + 编排 + 事务"，
    与 CLI 各写一份（缺陷 D4），且违反路由层不得直连存储的纪律（R3）。
    现在全部经 `MemoryService`，本文件不再出现 SQLiteStore。

`/api/memory/terminal` 的命令名与响应结构**刻意保持不变**
（前端 TerminalView.vue 与 tests/test_web_management.py 依赖它）；
变化只在于命令实现改为调用 service，不再自己写存储逻辑。
"""

import json
import shlex
from contextlib import contextmanager
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services.agent_runtime import AgentRuntime
from app.services.memory_service import MemoryService, MemoryServiceError

router = APIRouter(prefix="/api/memory")


@contextmanager
def service():
    """在 Agent 锁下提供 MemoryService，并把领域异常翻译为 HTTP 错误。"""
    with AgentRuntime.lock:
        try:
            yield MemoryService()
        except MemoryServiceError as error:
            raise _http_error(error) from error


def _http_error(error: MemoryServiceError) -> HTTPException:
    status = {
        "missing": 404,
        "exists": 409,
        "active": 409,
        "invalid_name": 422,
    }.get(error.code, 422)
    return HTTPException(status, str(error))


class MemoryInput(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=2000)


class Message(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(max_length=32000)


class Profile(BaseModel):
    user_name: str | None = Field(default=None, max_length=200)
    user_preferences: dict[str, str] = Field(default_factory=dict, max_length=100)
    key_facts: list[str] = Field(default_factory=list, max_length=200)
    relationship_stage: str = Field(default="new", max_length=100)
    conversation_summary: str = Field(default="", max_length=10000)


class MemoryUpdate(BaseModel):
    description: str = Field(default="", max_length=2000)
    profile: Profile | None = None
    messages: list[Message] | None = Field(default=None, max_length=2000)


class TerminalInput(BaseModel):
    command: str = Field(min_length=1, max_length=2000)
    confirm: bool = False


@router.get("")
def list_memories():
    with service() as memories:
        return {"ok": True, "data": memories.list_memories()}


@router.post("")
def create_memory(body: MemoryInput):
    with service() as memories:
        return {"ok": True, "data": memories.create_memory(body.name, body.description)}


@router.get("/{name}")
def get_memory(name: str):
    with service() as memories:
        return {"ok": True, "data": memories.get_memory(name)}


@router.put("/{name}")
def update_memory(name: str, body: MemoryUpdate):
    if body.profile and len(body.profile.model_dump_json()) > 100000:
        raise HTTPException(413, "长期记忆过大")
    with service() as memories:
        data = memories.update_memory(
            name,
            description=body.description,
            messages=None if body.messages is None else [item.model_dump() for item in body.messages],
            profile=None if body.profile is None else body.profile.model_dump(),
        )
    AgentRuntime.rebuild()
    return {"ok": True, "data": data}


@router.post("/{name}/activate")
def activate_memory(name: str):
    with service() as memories:
        active = memories.activate_memory(name)
    AgentRuntime.rebuild()
    return {"ok": True, "data": {"active": active}}


@router.delete("/{name}/messages")
def clear_memory(name: str):
    with service() as memories:
        data = memories.clear_memory(name)
    AgentRuntime.rebuild()
    return {"ok": True, "data": data}


@router.delete("/{name}")
def delete_memory(name: str):
    with service() as memories:
        return {"ok": True, "data": memories.delete_memory(name)}


# ── 终端视图：文本命令 → service 调用 ─────────────────────────────

TERMINAL_HELP = "list | show NAME | create NAME | use NAME | clear NAME | delete NAME | describe NAME TEXT"


@router.post("/terminal")
def terminal(body: TerminalInput):
    """把一行文本命令映射到 `MemoryService`。

    命令名与输出结构与历史实现一致；差异仅在实现改为调用 service。
    """
    try:
        args = shlex.split(body.command)
    except ValueError:
        raise HTTPException(422, "命令引号未闭合")
    if not args:
        raise HTTPException(422, "命令为空")

    command, *params = args

    if command == "help":
        return {"ok": True, "data": {"output": TERMINAL_HELP}}

    with service() as memories:
        if command == "list" and not params:
            result = memories.list_memories()
        elif command in {"show", "create", "use", "clear", "delete"} and len(params) == 1:
            if command in {"clear", "delete"} and not body.confirm:
                return {
                    "ok": True,
                    "data": {"confirmation_required": True, "output": "此操作将永久修改记忆"},
                }
            name = params[0]
            actions = {
                "show": memories.get_memory,
                "create": lambda value: memories.create_memory(value),
                "use": memories.activate_memory,
                "clear": memories.clear_memory,
                "delete": memories.delete_memory,
            }
            result = actions[command](name)
        elif command == "describe" and len(params) >= 2:
            memories.set_description(params[0], " ".join(params[1:]))
            result = memories.get_memory(params[0])
        else:
            raise HTTPException(422, "未知记忆命令，输入 help 查看命令")

    return {
        "ok": True,
        "data": {
            "output": result if isinstance(result, str) else json.dumps(result, ensure_ascii=False, indent=2)
        },
    }
