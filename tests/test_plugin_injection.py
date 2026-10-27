"""插件注入到 Agent 的契约。

分层规则禁止 `core` 依赖 `services`（R1），所以插件加载放在
`AgentRuntime._register_plugins` 里，由服务层注入。
这组测试锁住"注入"这一环，并且确认**插件故障不会阻止 Agent 启动**。
"""

import json
import textwrap

import pytest

from app.services.agent_runtime import AgentRuntime
from app.services import plugin_service

PLUGIN_CODE = '''
from app.core.tools.base import BaseTool


class Ping(BaseTool):
    name = "ping"
    description = "返回 pong"
    def execute(self, **kwargs):
        return "pong"


def tools():
    return [Ping()]
'''


def install_plugin(root, name="pinger", enabled=True, code=PLUGIN_CODE):
    directory = root / "data" / "plugins" / name
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "plugin.json").write_text(json.dumps({
        "name": name, "version": "1.0.0", "entry": "plugin.py", "enabled": enabled,
    }), encoding="utf-8")
    (directory / "plugin.py").write_text(textwrap.dedent(code), encoding="utf-8")


class StubAgent:
    """只提供 `_register_plugins` 需要的两个属性。"""

    def __init__(self):
        from app.core.tools.registry import ToolRegistry

        self.tool_registry = ToolRegistry()


@pytest.fixture
def repo(tmp_path, monkeypatch):
    """把 repo_root 指到临时目录，插件落在 tmp 下。"""
    import app.paths

    monkeypatch.setattr(app.paths, "repo_root", lambda: tmp_path)
    return tmp_path


def test_plugins_are_injected(repo):
    install_plugin(repo)
    agent = StubAgent()
    AgentRuntime._register_plugins(AgentRuntime.__new__(AgentRuntime), agent)
    assert agent.tool_registry.get("plugin_ping") is not None


def test_disabled_plugin_not_injected(repo):
    install_plugin(repo, enabled=False)
    agent = StubAgent()
    AgentRuntime._register_plugins(AgentRuntime.__new__(AgentRuntime), agent)
    assert agent.tool_registry.get("plugin_ping") is None


def test_broken_plugin_does_not_raise(repo):
    install_plugin(repo, name="broken", code="raise RuntimeError('boom')")
    agent = StubAgent()
    # 不应抛异常
    AgentRuntime._register_plugins(AgentRuntime.__new__(AgentRuntime), agent)
    assert agent.tool_registry.list_tools() == []


def test_plugin_failure_does_not_block_agent(repo, monkeypatch):
    """插件系统自身炸了也不能阻止 Agent 启动。"""
    def explode(*args, **kwargs):
        raise RuntimeError("plugin subsystem down")

    monkeypatch.setattr(plugin_service, "load", explode)
    agent = StubAgent()
    AgentRuntime._register_plugins(AgentRuntime.__new__(AgentRuntime), agent)
    # 走到这里没抛异常即为通过
    assert agent.tool_registry.list_tools() == []


def test_no_plugins_directory_is_fine(repo):
    agent = StubAgent()
    AgentRuntime._register_plugins(AgentRuntime.__new__(AgentRuntime), agent)
    assert agent.tool_registry.list_tools() == []
