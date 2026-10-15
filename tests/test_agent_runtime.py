"""AgentRuntime 生命周期契约（docs/DECISIONS_V0.2.md §7）。

P1 的目标是把"Agent 单例 / 重建 / 释放"从散落的 8 处路由调用收敛为单一入口。
本文件锁住三件容易被后续重构悄悄破坏的事：

1. 重建必须**释放**旧实例（Agent 持有 MCP 子进程，只丢引用会泄漏）；
2. 重建是**惰性**的，不取用就不构造；
3. 路由层不得再直接引用旧的 AgentManager。

用假 Agent 替换真实 Agent：本测试只验证生命周期编排，不触碰 LLM/MCP。
"""

from types import SimpleNamespace

import pytest

from app.config.runtime import RuntimeConfig
from app.services.agent_runtime import AgentRuntime


@pytest.fixture(autouse=True)
def isolate(tmp_path, monkeypatch):
    """隔离配置路径、角色存储与类级单例，避免污染真实 data/ 与其它用例。"""
    import app.config.runtime as runtime_module
    import app.core.persona as persona_module
    import app.services.agent_runtime as runtime_module_service

    monkeypatch.setattr(runtime_module, "CONFIG_PATH", tmp_path / "config.json")
    monkeypatch.setattr(persona_module, "PERSONAS_PATH", tmp_path / "personas.json")
    monkeypatch.setattr(persona_module.PersonaStore, "_instance", None)
    persona_module.PersonaStore.get()

    class FakeAgent:
        """最小可用假 Agent：只提供 AgentRuntime 真正用到的接口。"""

        created: list["FakeAgent"] = []

        def __init__(self, config, approval_callback=None):
            self.config = config
            self.approval_callback = approval_callback
            self.shutdown_calls = 0
            self.memory = SimpleNamespace(get_message=lambda: [], add_message=lambda **kw: None)
            self.persona = None
            FakeAgent.created.append(self)

        def shutdown(self):
            self.shutdown_calls += 1

        def stream_chat(self, user_input, **options):
            yield f"echo:{user_input}"

    FakeAgent.created = []
    monkeypatch.setattr(runtime_module_service, "Agent", FakeAgent)
    AgentRuntime.reset_for_tests()
    yield FakeAgent
    AgentRuntime.reset_for_tests()


def test_get_is_lazy_and_singleton(isolate):
    """首次 get() 才构造，之后复用同一实例。"""
    assert isolate.created == []
    first = AgentRuntime.get()
    second = AgentRuntime.get()
    assert first is second
    assert len(isolate.created) == 1


def test_instance_returns_none_before_first_use(isolate):
    """只读状态查询不应触发 Agent 构造。"""
    assert AgentRuntime.instance() is None
    assert isolate.created == []


def test_rebuild_is_lazy_and_releases_old_instance(isolate):
    """核心契约：重建释放旧实例（关闭 MCP），且不立即构造新的。"""
    old = AgentRuntime.get()
    assert old.shutdown_calls == 0

    AgentRuntime.rebuild()

    assert old.shutdown_calls == 1, "重建必须释放旧 Agent，否则 MCP 子进程泄漏"
    assert AgentRuntime.instance() is None
    assert len(isolate.created) == 1, "重建应惰性：不该在此刻构造新 Agent"

    new = AgentRuntime.get()
    assert new is not old
    assert len(isolate.created) == 2


def test_shutdown_releases_and_clears(isolate):
    """应用退出路径：立即释放并清空。"""
    agent = AgentRuntime.get()
    AgentRuntime.shutdown()
    assert agent.shutdown_calls == 1
    assert AgentRuntime.instance() is None


def test_shutdown_without_instance_is_noop(isolate):
    AgentRuntime.shutdown()
    assert isolate.created == []


def test_chat_records_latest_message(isolate):
    """send() 汇总流式输出并记录 latest_message。"""
    assert AgentRuntime.chat("hello") == "echo:hello"
    assert AgentRuntime.latest_message() == "echo:hello"

    AgentRuntime.set_latest_message("")
    assert AgentRuntime.latest_message() == ""


def test_rebuild_clears_latest_message(isolate):
    AgentRuntime.chat("hello")
    assert AgentRuntime.latest_message() == "echo:hello"
    AgentRuntime.rebuild()
    assert AgentRuntime.latest_message() == ""


def test_approval_callback_is_injected_into_agent(isolate):
    """审批回调透传到 Agent 构造（§9），未传时为 None → fail-safe 拒绝。"""
    sentinel = lambda tool, kwargs: True  # noqa: E731
    runtime = AgentRuntime(approval_callback=sentinel)
    assert runtime.agent().approval_callback is sentinel

    runtime.invalidate()
    default_runtime = AgentRuntime()
    assert default_runtime.agent().approval_callback is None


def test_individual_instances_do_not_share_state(isolate):
    """实例模式（CLI/测试用）与类级单例互不影响。"""
    runtime_a = AgentRuntime()
    runtime_b = AgentRuntime()
    assert runtime_a.agent() is not runtime_b.agent()
    assert len(isolate.created) == 2

    runtime_a.invalidate()
    assert runtime_a.current() is None, "invalidate 后旧实例应已释放"
    assert runtime_b.current() is not None, "invalidate 不得影响其它实例"
    assert len(isolate.created) == 2, "invalidate 是惰性的，不该立即重建"


def test_web_routes_no_longer_reference_agent_manager():
    """P1 验收：旧 AgentManager 已删除，routes 不再引用它。

    这是文本级检查（对应文档里的 grep 验收标准），因为该字符串是重构
    痕迹而非语义依赖，用 AST 反而看不出"是否还提到旧名字"。
    """
    from pathlib import Path

    routes = Path(__file__).resolve().parents[1] / "app" / "interfaces" / "web" / "routes"
    offenders = [
        path.name
        for path in sorted(routes.rglob("*.py"))
        if "AgentManager" in path.read_text(encoding="utf-8")
    ]
    assert not offenders, f"routes 仍在引用 AgentManager: {offenders}"


def test_old_modules_are_gone():
    """P1 删除的模块不得复活；P5 后按新路径检查。"""
    from pathlib import Path

    app = Path(__file__).resolve().parents[1] / "app"
    assert not (app / "interfaces" / "web" / "agent_manager.py").exists()
    assert not (app / "core" / "session.py").exists()


def test_dead_code_removed_in_p6():
    """P6 清理项不得复活：命令转发层、CLI chat 空壳、废弃子命令、空目录。"""
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    app = root / "app"

    assert not (app / "interfaces" / "commands" / "handler.py").exists()
    assert not (app / "interfaces" / "cli" / "chat.py").exists()
    for name in ("static", "ui", "utils"):
        assert not (app / name).exists(), f"空的遗留目录 app/{name}/ 又出现了"

    source = (app / "interfaces" / "cli" / "start.py").read_text(encoding="utf-8")
    assert "deprecated=True" not in source, "start.py 又出现了废弃占位子命令"
    assert "live_2d" not in source and "def fastapi" not in source

    app_source = (app / "interfaces" / "cli" / "app.py").read_text(encoding="utf-8")
    assert "chat_app" not in app_source, "废弃的 chat 子命令又注册回来了"
