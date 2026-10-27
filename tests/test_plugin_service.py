"""插件系统的契约测试。

插件是"执行任意用户代码"，所以重点不在功能多寡，而在**边界**：

    * 未启用不加载（文件存在 ≠ 允许执行）；
    * 坏插件只跳过，不拖垮 Agent；
    * 工具名必须带 `plugin_` 前缀，不能覆盖内置工具；
    * tools() 缺失 / 抛异常 / 返回空 都要有清晰原因。
"""

import json
import textwrap

import pytest

from app.services import plugin_service as plugins

PLUGIN_CODE = '''
from app.core.tools.base import BaseTool, ToolParameter


class Echo(BaseTool):
    name = "echo"
    description = "原样返回文本"
    parameters = [ToolParameter(name="text", type="string", description="文本")]

    def execute(self, **kwargs):
        return str(kwargs.get("text", ""))


def tools():
    return [Echo()]
'''


def make_plugin(root, name="demo", *, enabled=True, version="1.0.0",
                entry="plugin.py", code=PLUGIN_CODE, manifest=True):
    directory = root / "data" / "plugins" / name
    directory.mkdir(parents=True, exist_ok=True)
    if manifest:
        payload = {"name": name, "version": version, "description": "测试插件",
                   "entry": entry, "enabled": enabled}
        (directory / "plugin.json").write_text(
            json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    if code is not None:
        (directory / entry).write_text(textwrap.dedent(code), encoding="utf-8")
    return directory


# ── 发现与清单 ────────────────────────────────────────────────────

def test_discover_empty(tmp_path):
    assert plugins.discover(tmp_path) == []


def test_discover_reads_manifest(tmp_path):
    make_plugin(tmp_path, "alpha", enabled=True)
    make_plugin(tmp_path, "beta", enabled=False)
    found = plugins.discover(tmp_path)
    assert [item.name for item in found] == ["alpha", "beta"]
    assert found[0].enabled is True
    assert found[1].enabled is False


def test_disabled_is_default(tmp_path):
    """清单里没写 enabled 时默认关闭——文件存在不等于允许执行。"""
    directory = make_plugin(tmp_path, "gamma", enabled=True)
    payload = json.loads((directory / "plugin.json").read_text(encoding="utf-8"))
    payload.pop("enabled")
    (directory / "plugin.json").write_text(json.dumps(payload), encoding="utf-8")
    assert plugins.discover(tmp_path)[0].enabled is False


def test_missing_manifest_reported(tmp_path):
    make_plugin(tmp_path, "broken", manifest=False)
    info = plugins.discover(tmp_path)[0]
    assert "plugin.json" in info.error


def test_invalid_json_reported(tmp_path):
    directory = make_plugin(tmp_path, "bad")
    (directory / "plugin.json").write_text("{oops", encoding="utf-8")
    assert "JSON" in plugins.discover(tmp_path)[0].error


def test_missing_required_fields(tmp_path):
    directory = make_plugin(tmp_path, "nofields")
    (directory / "plugin.json").write_text(json.dumps({"description": "x"}), encoding="utf-8")
    assert "缺少字段" in plugins.discover(tmp_path)[0].error


def test_entry_must_be_local_file(tmp_path):
    directory = make_plugin(tmp_path, "escape")
    (directory / "plugin.json").write_text(json.dumps({
        "name": "escape", "version": "1.0", "entry": "../evil.py", "enabled": True,
    }), encoding="utf-8")
    assert "entry" in plugins.discover(tmp_path)[0].error


def test_missing_entry_file(tmp_path):
    make_plugin(tmp_path, "noentry", entry="runner.py", code=None)
    assert "缺少入口文件" in plugins.discover(tmp_path)[0].error


# ── 加载 ──────────────────────────────────────────────────────────

def test_load_enabled_plugin(tmp_path):
    make_plugin(tmp_path, "demo", enabled=True)
    result = plugins.load(tmp_path)
    assert result.loaded == ["demo"]
    assert len(result.tools) == 1
    assert result.tools[0].name == "plugin_echo"
    assert result.tools[0].execute(text="hi") == "hi"


def test_disabled_plugin_is_not_executed(tmp_path):
    make_plugin(tmp_path, "demo", enabled=False)
    result = plugins.load(tmp_path)
    assert result.tools == []
    assert result.loaded == []
    assert ("demo", "未启用") in result.skipped


def test_broken_plugin_does_not_break_others(tmp_path):
    make_plugin(tmp_path, "good", enabled=True)
    make_plugin(tmp_path, "bad", enabled=True, code="raise RuntimeError('boom')")
    result = plugins.load(tmp_path)
    assert result.loaded == ["good"]
    assert len(result.tools) == 1
    assert any(name == "bad" for name, _reason in result.skipped)


def test_missing_tools_function(tmp_path):
    make_plugin(tmp_path, "nofunc", enabled=True, code="VALUE = 1")
    result = plugins.load(tmp_path)
    assert any("tools()" in reason for _name, reason in result.skipped)


def test_tools_raising_is_reported(tmp_path):
    make_plugin(tmp_path, "boom", enabled=True,
                code="def tools():\n    raise ValueError('nope')")
    result = plugins.load(tmp_path)
    assert any("tools() 执行失败" in reason for _name, reason in result.skipped)


def test_empty_tools_reported(tmp_path):
    make_plugin(tmp_path, "empty", enabled=True, code="def tools():\n    return []")
    result = plugins.load(tmp_path)
    assert any("没有返回任何工具" in reason for _name, reason in result.skipped)


def test_tool_without_name_reported(tmp_path):
    make_plugin(tmp_path, "noname", enabled=True, code=textwrap.dedent('''
        class Broken:
            description = "x"
            def execute(self, **kwargs):
                return ""
        def tools():
            return [Broken()]
    '''))
    result = plugins.load(tmp_path)
    assert any("name" in reason for _name, reason in result.skipped)


def test_tool_names_are_prefixed(tmp_path):
    make_plugin(tmp_path, "pref", enabled=True, code=textwrap.dedent('''
        from app.core.tools.base import BaseTool
        class T(BaseTool):
            name = "dangerous_name"
            description = "x"
            def execute(self, **kwargs):
                return "ok"
        def tools():
            return [T()]
    '''))
    result = plugins.load(tmp_path)
    assert result.tools[0].name == "plugin_dangerous_name"


def test_cannot_override_builtin_tool(tmp_path):
    """插件工具一律加前缀，内置工具不会被顶掉。"""
    from app.core.tools.registry import ToolRegistry

    class Builtin:
        name = "plugin_existing"
        description = "builtin"
        def execute(self, **kwargs):
            return "builtin"

    registry = ToolRegistry()
    registry.register(Builtin())  # type: ignore[arg-type]

    make_plugin(tmp_path, "clash", enabled=True, code=textwrap.dedent('''
        from app.core.tools.base import BaseTool
        class T(BaseTool):
            name = "existing"
            description = "x"
            def execute(self, **kwargs):
                return "plugin"
        def tools():
            return [T()]
    '''))
    result = plugins.load(tmp_path, tool_registry=registry)
    assert result.tools == []
    assert any("冲突" in reason for _name, reason in result.skipped)


def test_load_registers_into_registry(tmp_path):
    from app.core.tools.registry import ToolRegistry

    make_plugin(tmp_path, "reg", enabled=True)
    registry = ToolRegistry()
    result = plugins.load(tmp_path, tool_registry=registry)
    assert result.tools
    assert registry.get("plugin_echo") is not None


# ── 启用/停用 ─────────────────────────────────────────────────────

def test_set_enabled_roundtrip(tmp_path):
    make_plugin(tmp_path, "toggle", enabled=False)
    assert plugins.set_enabled(tmp_path, "toggle", True) is True
    assert plugins.discover(tmp_path)[0].enabled is True
    assert plugins.set_enabled(tmp_path, "toggle", False) is True
    assert plugins.discover(tmp_path)[0].enabled is False


def test_set_enabled_unknown_returns_false(tmp_path):
    assert plugins.set_enabled(tmp_path, "nope", True) is False


def test_plugins_root_is_under_data(tmp_path):
    assert plugins.plugins_root(tmp_path).parent.name == "data"
