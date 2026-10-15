"""审批回调注入契约（docs/DECISIONS_V0.2.md §9）。

回归目标（缺陷 D3）：审批模式必须由**构造参数**决定，而不是由调用方事后
覆盖 `tool_manager._guard`。历史实现里 `Agent` 内建 CLI 回调、Web 再打补丁覆盖，
导致两端审批语义不一致。

这些测试只断言"回调是否被传入并生效"，不重复 `tests/test_tools_guard.py`
已覆盖的 ToolGuard 分级逻辑。
"""

import pytest

from app.config.runtime import RuntimeConfig
from app.core.agent import Agent
from app.core.tools.base import BaseTool, DangerLevel
from app.core.tools.guard import ToolGuard

# 每个测试里真实构造 Agent，不 mock ToolGuard —— 这正是本测试要锁的行为


class DangerousTool(BaseTool):
    name = "dangerous_probe"
    description = "用于验证审批链路的危险工具"
    parameters = []
    danger_level = DangerLevel.DANGEROUS

    def execute(self, **kwargs) -> str:
        return "executed"


@pytest.fixture
def config(tmp_path):
    return RuntimeConfig(db_path=str(tmp_path / "approval.db"))


@pytest.fixture(autouse=True)
def isolate_personas(tmp_path, monkeypatch):
    """隔离角色存储与配置路径，避免污染真实 data/。"""
    import app.core.persona as persona_module
    import app.config.runtime as runtime_module

    monkeypatch.setattr(persona_module, "PERSONAS_PATH", tmp_path / "personas.json")
    monkeypatch.setattr(runtime_module, "CONFIG_PATH", tmp_path / "config.json")
    monkeypatch.setattr(persona_module.PersonaStore, "_instance", None)
    persona_module.PersonaStore.get()
    yield


def test_agent_without_callback_denies_dangerous_tool(config):
    """Web 路径：不传回调 → approval_mode 为 auto-deny 且危险工具被拒绝。"""
    agent = Agent(config)

    assert agent.approval_mode == "auto-deny"
    assert agent.tool_manager._guard.check(DangerousTool(), {}) is False


def test_agent_with_callback_uses_it(config):
    """CLI 路径：传入回调 → approval_mode 为 interactive 且回调被调用。"""
    calls = []

    def callback(tool, kwargs):
        calls.append(tool.name)
        return True

    agent = Agent(config, approval_callback=callback)

    assert agent.approval_mode == "interactive"
    assert agent.tool_manager._guard.check(DangerousTool(), {}) is True
    assert calls == ["dangerous_probe"]


def test_callback_rejection_is_respected(config):
    """回调拒绝 → 危险工具被拦截。"""
    agent = Agent(config, approval_callback=lambda tool, kwargs: False)

    assert agent.tool_manager._guard.check(DangerousTool(), {}) is False


def test_approval_callback_is_not_imported_from_core():
    """core 不得内建 CLI 审批实现（依赖方向 R1 的语义保证）。"""
    import app.core.agent as agent_module

    assert not hasattr(agent_module, "cli_approval_callback")
    # 回调实现应位于交互层
    from app.interfaces.cli.approval import cli_approval_callback

    assert callable(cli_approval_callback)


def test_guard_default_remains_fail_safe():
    """不回归：guard 自身的 fail-safe 默认值不变。"""
    assert ToolGuard().check(DangerousTool(), {}) is False
