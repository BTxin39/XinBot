"""记忆与角色 service 的契约测试（docs/DECISIONS_V0.2.md §5.2、P3）。

P3 收敛了两个跨端缺陷：
    D1 —— 切换角色时是否同时切换记忆上下文，此前只有 Web 做，CLI 不做；
    D4 —— 记忆读写路径，此前 CLI 走 ChatMemory 缓存、Web 直连 SQLiteStore。

本文件锁住：
  1. 角色-记忆命名的**唯一实现**，并证明 CLI 与 Web 两条路径得到相同结果；
  2. ChatMemory 能感知外部进程对 SQLite 的改动（缓存一致性）；
  3. service 的领域异常语义（供适配器翻译）。
"""

from pathlib import Path

import pytest

from app.config.runtime import RuntimeConfig
from app.core.persona import Persona, PersonaStore
from app.memory.chat_memory import ChatMemory
from app.services.memory_service import (
    MemoryService,
    MemoryServiceError,
    is_valid_memory_name,
    memory_name_for_persona,
)
from app.services.persona_service import PersonaService, PersonaServiceError


@pytest.fixture
def config(tmp_path, monkeypatch):
    """把配置路径、角色存储、画像目录全部隔离到 tmp_path。"""
    import app.config.runtime as runtime_module
    import app.core.persona as persona_module
    import app.services.memory_service as memory_module

    monkeypatch.setattr(runtime_module, "CONFIG_PATH", tmp_path / "config.json")
    monkeypatch.setattr(persona_module, "PERSONAS_PATH", tmp_path / "personas.json")
    monkeypatch.setattr(memory_module, "PROFILE_DIR", tmp_path / "profiles")
    monkeypatch.setattr(persona_module.PersonaStore, "_instance", None)
    PersonaStore.get()

    result = RuntimeConfig(db_path=str(tmp_path / "memory.db"), current_memory_name="default")
    result.save()
    return result


# ── D1：命名与激活语义只有一个实现 ────────────────────────────────


def test_persona_memory_naming_is_centralized():
    assert memory_name_for_persona("shiro") == "web-shiro"


def test_activate_sets_persona_and_memory(config):
    """激活角色必须同时切换记忆上下文（D1 的统一实现）。"""
    service = PersonaService(config)
    service.store.add_persona(Persona(name="test-shiro", display_name="Shiro", builtin=False))

    service.activate("test-shiro")

    reloaded = RuntimeConfig.load()
    assert reloaded.persona_name == "test-shiro"
    assert reloaded.current_memory_name == memory_name_for_persona("test-shiro")


def test_cli_and_web_activation_converge_on_same_memory(config):
    """回归锚点：CLI 的 `persona set` 与 Web 的 activate 必须落到同一记忆名。

    历史缺陷（D1）：CLI 只改 persona_name，Web 还改 current_memory_name，
    导致同一角色在两端进入不同记忆空间。
    """
    service = PersonaService(config)
    service.store.add_persona(Persona(name="test-mentor", display_name="Senpai", builtin=False))

    # Web 路径：PersonaService.activate
    service.activate("test-mentor")
    web_memory = RuntimeConfig.load().current_memory_name

    # CLI 路径：同样的 service 方法（app/interfaces/cli/persona.py 已改为调用它）
    RuntimeConfig(db_path=config.db_path, current_memory_name="default").save()
    PersonaService(RuntimeConfig.load()).activate("test-mentor")
    cli_memory = RuntimeConfig.load().current_memory_name

    assert web_memory == cli_memory == "web-test-mentor"


def test_activate_missing_persona_raises(config):
    with pytest.raises(PersonaServiceError) as excinfo:
        PersonaService(config).activate("nobody")
    assert excinfo.value.code == "missing"


def test_delete_active_persona_refused(config):
    service = PersonaService(config)
    service.store.add_persona(Persona(name="test-shiro", display_name="Shiro", builtin=False))
    service.activate("test-shiro")

    with pytest.raises(PersonaServiceError) as excinfo:
        PersonaService(RuntimeConfig.load()).delete("test-shiro")
    assert excinfo.value.code == "active"


# ── MemoryService 语义 ────────────────────────────────────────────


def test_memory_name_validation():
    assert is_valid_memory_name("web-shiro")
    assert is_valid_memory_name("a_b-1")
    assert not is_valid_memory_name("../escape")
    assert not is_valid_memory_name("")
    assert not is_valid_memory_name("a" * 101)


def test_create_read_update_delete_cycle(config):
    service = MemoryService(config)

    service.create_memory("scratch", "desc")
    assert "scratch" in [item["name"] for item in service.list_memories()]

    service.update_memory("scratch", messages=[{"role": "user", "content": "hi"}])
    detail = service.get_memory("scratch")
    assert detail["messages"] == [{"role": "user", "content": "hi"}]
    assert detail["description"] == "desc"

    service.clear_memory("scratch")
    assert service.get_memory("scratch")["messages"] == []
    # 清空不应丢描述
    assert service.get_memory("scratch")["description"] == "desc"

    service.delete_memory("scratch")
    with pytest.raises(MemoryServiceError) as excinfo:
        service.get_memory("scratch")
    assert excinfo.value.code == "missing"


def test_duplicate_create_conflicts(config):
    service = MemoryService(config)
    service.create_memory("dup")
    with pytest.raises(MemoryServiceError) as excinfo:
        service.create_memory("dup")
    assert excinfo.value.code == "exists"


def test_delete_active_memory_refused(config):
    service = MemoryService(config)
    service.create_memory("keep")
    service.activate_memory("keep")

    with pytest.raises(MemoryServiceError) as excinfo:
        MemoryService(RuntimeConfig.load()).delete_memory("keep")
    assert excinfo.value.code == "active"


def test_invalid_name_rejected_before_touching_storage(config):
    service = MemoryService(config)
    with pytest.raises(MemoryServiceError) as excinfo:
        service.create_memory("../escape")
    assert excinfo.value.code == "invalid_name"


def test_activate_persona_memory_allows_not_yet_existing(config):
    """首次切换到某角色时该记忆还不存在，属合法状态。"""
    service = MemoryService(config)
    name = service.activate_persona_memory("brand-new")
    assert name == "web-brand-new"
    assert RuntimeConfig.load().current_memory_name == name


def test_list_always_includes_active_memory(config):
    """即使激活的记忆还没有任何消息，也必须出现在列表里。"""
    MemoryService(config).activate_persona_memory("ghost")
    names = [item["name"] for item in MemoryService(config).list_memories()]
    assert "web-ghost" in names


def test_profile_roundtrip(config):
    service = MemoryService(config)
    service.create_memory("profiled")
    service.write_profile("profiled", {"user_name": "Tester"})
    assert service.get_memory("profiled")["profile"] == {"user_name": "Tester"}

    service.update_memory("profiled", profile={"user_name": "Updated"})
    assert service.read_profile("profiled") == {"user_name": "Updated"}

    service.delete_memory("profiled")
    assert service.read_profile("profiled") == {}


# ── D4：CLI 进程的缓存一致性 ──────────────────────────────────────


def test_chat_memory_detects_external_message_inserts(config):
    """外部进程写入消息后，常驻的 ChatMemory 必须能感知（D4）。"""
    cached = ChatMemory(config)
    assert cached.get_message() == []

    # 模拟"另一个进程"（Web）往同一记忆写入
    MemoryService(RuntimeConfig.load()).update_memory(
        config.current_memory_name or "default",
        messages=[{"role": "user", "content": "from web"}],
    )

    assert cached.sync_if_stale() is True
    assert [item["content"] for item in cached.get_message()] == ["from web"]


def test_chat_memory_detects_external_memory_switch(config):
    """外部进程切换激活记忆后，常驻 ChatMemory 必须跟着切。"""
    cached = ChatMemory(config)
    assert cached._current_memory_name == "default"

    MemoryService(RuntimeConfig.load()).activate_persona_memory("shiro")

    assert cached.sync_if_stale() is True
    assert cached._current_memory_name == "web-shiro"


def test_chat_memory_reports_no_change_when_clean(config):
    cached = ChatMemory(config)
    cached.add_message(role="user", content="local")
    assert cached.sync_if_stale() is False
    assert len(cached.get_message()) == 1


def test_memory_manager_exposes_sync(config):
    """MemoryManager 需把缓存同步能力暴露给 Agent。"""
    from app.memory.manager import MemoryManager

    manager = MemoryManager(config)
    assert manager.sync_if_stale() is False
    manager.add_message(role="user", content="hello")
    assert [item["content"] for item in manager.get_message()] == ["hello"]
