"""AgentRuntime 的类方法契约（v0.2.1 回归）。

P1 把 `refresh_persona` 写成了**实例方法**，而路由以
`AgentRuntime.refresh_persona(name)` 方式调用 —— `name` 被当成 `self`，
抛 `TypeError: missing 1 required positional argument: 'name'`，
表现为"编辑角色必 500"。当时没有测试覆盖 PUT /api/persona/{name}，
所以一直没暴露。
"""

import pytest

from app.config.runtime import RuntimeConfig
from app.core.persona import Persona, PersonaStore
from app.services.agent_runtime import AgentRuntime
from tests.test_web_cards import client as web_client  # noqa: F401  (pytest fixture)


@pytest.fixture
def ready_runtime(tmp_path, monkeypatch):
    """隔离配置/角色存储，并准备一个运行中的 Agent。"""
    import app.config.runtime as runtime_module
    import app.core.persona as persona_module
    import app.services.agent_runtime as runtime_module_service

    monkeypatch.setattr(runtime_module, "CONFIG_PATH", tmp_path / "config.json")
    monkeypatch.setattr(persona_module, "PERSONAS_PATH", tmp_path / "personas.json")
    monkeypatch.setattr(persona_module.PersonaStore, "_instance", None)
    PersonaStore.get()

    config = RuntimeConfig(db_path=str(tmp_path / "m.db"))
    config.save()
    AgentRuntime.reset_for_tests()
    yield
    AgentRuntime.reset_for_tests()


def test_refresh_persona_is_callable_as_classmethod(ready_runtime):
    """必须以 `AgentRuntime.refresh_persona(name)` 形式调用（路由就是这么写的）。"""
    store = PersonaStore.get()
    store.add_persona(Persona(name="test-a", display_name="A"))

    config = RuntimeConfig.load()
    config.persona_name = "test-a"
    config.save()

    agent = AgentRuntime.get()
    assert agent.config.persona_name == "test-a"

    # 关键：不是 agent_instance.refresh_persona(...)
    updated = AgentRuntime.refresh_persona("test-a")
    assert updated is True

    # 改角色再刷新，运行实例应拿到新数据
    store.update_persona("test-a", {"display_name": "A-updated"})
    assert AgentRuntime.refresh_persona("test-a") is True
    assert AgentRuntime.get().persona.display_name == "A-updated"


def test_refresh_persona_ignores_other_persona(ready_runtime):
    """运行中的 Agent 不是该角色时不做任何事。"""
    PersonaStore.get().add_persona(Persona(name="test-b", display_name="B"))
    RuntimeConfig(db_path=str(RuntimeConfig.load().db_path)).save()

    config = RuntimeConfig.load()
    config.persona_name = "xin"
    config.save()
    AgentRuntime.get()

    assert AgentRuntime.refresh_persona("test-b") is False


def test_refresh_persona_without_instance_is_noop(ready_runtime):
    assert AgentRuntime.instance() is None
    assert AgentRuntime.refresh_persona("xin") is False


def test_web_persona_update_does_not_500(web_client):
    """端到端：PUT /api/persona/{name} 不能再抛 500。"""
    created = web_client.post("/api/persona", json={"display_name": "更新测试"})
    assert created.status_code == 200
    name = created.json()["data"]["name"]

    # 先让它成为激活角色并触发一次 Agent 构造，覆盖"热更新"分支
    assert web_client.post(f"/api/persona/{name}/activate").status_code == 200

    updated = web_client.put(f"/api/persona/{name}", json={"display_name": "更新后"})
    assert updated.status_code == 200, updated.text
    assert updated.json()["data"]["display_name"] == "更新后"
