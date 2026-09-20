from contextlib import contextmanager
import json
from pathlib import Path
import re
import shlex
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.config.runtime import RuntimeConfig
from app.storage.sqlite_store import SQLiteStore
from app.web.agent_manager import AgentManager

router = APIRouter(prefix="/api/memory")
PROFILE_ROOT = Path("data/memory_json")


def safe_name(name):
    if not re.fullmatch(r"[\w-]{1,100}", name):
        raise HTTPException(422, "记忆名称只能包含字母、数字、下划线和连字符")
    return name


@contextmanager
def storage():
    with AgentManager.lock:
        store = SQLiteStore(RuntimeConfig.load().db_path)
        try:
            yield store
        finally:
            store.engine.dispose()


def profile_path(name):
    return PROFILE_ROOT / f"{safe_name(name)}_profile.json"


def require_memory(store, name):
    safe_name(name)
    if name not in store.get_memory_list() and name != RuntimeConfig.load().current_memory_name:
        raise HTTPException(404, "记忆不存在")


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


@router.get("")
def list_memories():
    with storage() as store:
        current = RuntimeConfig.load().current_memory_name
        names = sorted(set(store.get_memory_list()) | {current})
        return {"ok": True, "data": [{"name": name, "description": store.get_description(name),
                                      "count": store.get_message_count(name), "active": name == current} for name in names]}


@router.post("")
def create_memory(body: MemoryInput):
    safe_name(body.name)
    with storage() as store:
        if body.name in store.get_memory_list() or body.name == RuntimeConfig.load().current_memory_name:
            raise HTTPException(409, "记忆已存在")
        store.set_description(body.name, body.description)
        store.mark_migrated(body.name)
    return {"ok": True, "data": {"name": body.name}}


class TerminalInput(BaseModel):
    command: str = Field(min_length=1, max_length=2000)
    confirm: bool = False


@router.post("/terminal")
def terminal(body: TerminalInput):
    try:
        args = shlex.split(body.command)
    except ValueError:
        raise HTTPException(422, "命令引号未闭合")
    if not args:
        raise HTTPException(422, "命令为空")
    command, *params = args
    if command == "help":
        result = "list | show NAME | create NAME | use NAME | clear NAME | delete NAME | describe NAME TEXT"
    elif command == "list" and not params:
        result = list_memories()["data"]
    elif command in {"show", "create", "use", "clear", "delete"} and len(params) == 1:
        if command in {"clear", "delete"} and not body.confirm:
            return {"ok": True, "data": {"confirmation_required": True, "output": "此操作将永久修改记忆"}}
        actions = {"show": get_memory, "create": lambda name: create_memory(MemoryInput(name=name)),
                   "use": activate_memory, "clear": clear_memory, "delete": delete_memory}
        result = actions[command](params[0])["data"]
    elif command == "describe" and len(params) >= 2:
        result = update_memory(params[0], MemoryUpdate(description=" ".join(params[1:])))["data"]
    else:
        raise HTTPException(422, "未知记忆命令，输入 help 查看命令")
    return {"ok": True, "data": {"output": result if isinstance(result, str) else json.dumps(result, ensure_ascii=False, indent=2)}}


@router.get("/{name}")
def get_memory(name: str):
    with storage() as store:
        require_memory(store, name)
        path = profile_path(name)
        profile = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else Profile().model_dump()
        return {"ok": True, "data": {"name": name, "description": store.get_description(name),
                                      "messages": store.get_messages(name), "profile": profile}}


@router.put("/{name}")
def update_memory(name: str, body: MemoryUpdate):
    with storage() as store:
        require_memory(store, name)
        if body.profile and len(body.profile.model_dump_json()) > 100000:
            raise HTTPException(413, "长期记忆过大")
        store.set_description(name, body.description)
        if body.messages is not None:
            store.replace_messages(name, [message.model_dump() for message in body.messages])
        if body.profile is not None:
            path = profile_path(name)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(body.profile.model_dump_json(indent=2), encoding="utf-8")
        AgentManager.shutdown()
    return get_memory(name)


@router.post("/{name}/activate")
def activate_memory(name: str):
    with storage() as store:
        require_memory(store, name)
        config = RuntimeConfig.load()
        config.current_memory_name = name
        config.save()
        AgentManager.shutdown()
    return {"ok": True, "data": {"active": name}}


@router.delete("/{name}/messages")
def clear_memory(name: str):
    with storage() as store:
        require_memory(store, name)
        store.mark_migrated(name)
        store.set_description(name, store.get_description(name))
        store.clear_messages(name)
        AgentManager.shutdown()
    return {"ok": True, "data": {"cleared": name}}


@router.delete("/{name}")
def delete_memory(name: str):
    with storage() as store:
        require_memory(store, name)
        if RuntimeConfig.load().current_memory_name == name:
            raise HTTPException(409, "请先切换到其他记忆")
        store.delete_memory(name)
        profile_path(name).unlink(missing_ok=True)
    return {"ok": True, "data": {"deleted": name}}
