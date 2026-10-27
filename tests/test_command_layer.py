"""命令层契约（docs/DECISIONS/DECISIONS_V0.2.0.md §6）。

P2 的目标是让命令逻辑可被 Web 复用。关键是"命令层不再依赖 rich"——
这不能靠肉眼检查，所以本文件用 `sys.modules` 做**可执行证明**：
在干净子进程里导入命令层后，`rich` 不得出现在已加载模块中。

另附命令本身的行为回归：结构化结果必须携带渲染所需数据，
且结果里不得混入富文本标记（历史实现曾把 role 名当富文本样式输出）。
"""

import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.interfaces.commands import format as command_format
from app.interfaces.commands.registry import CommandHandler
from app.interfaces.commands.result import AFFIRM, CONFIRMATION, TABLE, TEXT, CommandResult

ROOT = Path(__file__).resolve().parents[1]


# ── 依赖纪律：可执行的证明 ────────────────────────────────────────


def test_command_layer_imports_with_rich_blocked():
    """在**禁用 rich** 的解释器里导入命令层必须成功。

    这是 P2 的核心验收：只有命令层不再需要 rich，Web 才能复用同一套命令。

    为什么不用"检查 sys.modules 里有没有 rich"：
    第三方依赖 `openai` / `chromadb` 自身会 import rich（实测各带入 55 个
    rich 子模块），所以"干净子进程里没有 rich"这个前提本身不成立，
    那样的断言会变成假失败。禁用导入才是对"我们的代码是否需要 rich"的
    直接证明。
    """
    code = (
        "import sys\n"
        "class Blocker:\n"
        "    def find_spec(self, name, path=None, target=None):\n"
        "        if name == 'rich' or name.startswith('rich.'):\n"
        "            raise ImportError('rich is blocked for this check')\n"
        "        return None\n"
        "sys.meta_path.insert(0, Blocker())\n"
        "import app.interfaces.commands.registry, app.interfaces.commands.result, app.interfaces.commands.format\n"
        "# 顺带确认命令真的能跑出结果（不只是 import 成功）\n"
        "from app.interfaces.commands.result import table\n"
        "assert table('t', ['a'], [['b']]).kind == 'table'\n"
        "print('OK')\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True, timeout=60
    )
    assert result.returncode == 0, f"命令层仍需要 rich：{result.stdout}{result.stderr}"


def test_command_layer_source_has_no_rich_imports():
    """命令层源码中不得出现 rich 导入语句（静态兜底）。"""
    offenders = []
    for path in (ROOT / "app" / "interfaces" / "commands").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for lineno, line in enumerate(text.splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith(("import rich", "from rich")):
                offenders.append(f"{path.name}:{lineno}")
    assert not offenders, f"app/interfaces/commands 下仍有 rich 导入：{offenders}"


def test_rich_renderer_lives_outside_command_layer():
    """rich 渲染位于 CLI 侧。"""
    assert (ROOT / "app" / "interfaces" / "cli" / "command_render.py").is_file()
    source = (ROOT / "app" / "interfaces" / "cli" / "command_render.py").read_text(encoding="utf-8")
    assert "rich.table" in source


# ── 命令行为回归 ─────────────────────────────────────────────────


class FakeMemory:
    def __init__(self, messages=None):
        self.messages = list(messages or [])
        self.cleared = 0

    def get_message(self):
        return self.messages

    def clear(self):
        self.cleared += 1
        self.messages.clear()


class FakeAgent:
    def __init__(self, messages=None, config=None, status=None):
        self.memory = FakeMemory(messages)
        self.config = config or SimpleNamespace(
            model_name="m", provider="p", temperature=0.7, max_memory_messages=20
        )
        self._status = status or SimpleNamespace(
            emotion="normal", provider="p", model_name="m", memory_messages=0
        )
        self.emotion = None
        self.remember_calls = 0

    def change_emotion(self, emotion):
        self.emotion = emotion

    def get_status(self):
        return self._status

    def remember_now(self):
        self.remember_calls += 1
        return "记忆已保存"


@pytest.fixture
def handler():
    return CommandHandler(FakeAgent())


def test_non_command_returns_none(handler):
    """不以 / 开头 → 交给 LLM（P2 后由 None 表达，而非 False）。"""
    assert handler.handle("hello there") is None
    assert handler.handle("") is None


def test_unknown_command_returns_help_text(handler):
    result = handler.handle("/nope")
    assert isinstance(result, CommandResult)
    assert result.kind == TEXT
    assert result.payload["title"] == "UNKNOWN COMMAND"
    assert "/help" in result.payload["body"]


@pytest.mark.parametrize(
    "name,expected_emotion",
    [("happy", "happy"), ("sad", "sad"), ("angry", "angry"), ("sleepy", "sleepy"), ("normal", "normal")],
)
def test_emotion_commands_bind_their_own_value(name, expected_emotion, handler):
    """情绪命令的闭包必须绑定自己的值（历史实现曾有闭包捕获问题）。"""
    result = handler.handle(f"/{name}")
    assert result.kind == AFFIRM
    assert handler.agent.emotion == expected_emotion
    assert result.payload["message"] == f"Emotion -> {expected_emotion}"


def test_help_returns_table(handler):
    result = handler.handle("/help")
    assert result.kind == TABLE
    assert result.payload["columns"] == ["Command", "Description"]
    names = [row[0] for row in result.payload["rows"]]
    assert "/help" in names and "/history" in names and "/remember" in names


def test_clear_calls_memory_and_affirms(handler):
    handler.agent.memory.messages.append({"role": "user", "content": "x"})
    result = handler.handle("/clear")
    assert result.kind == AFFIRM
    assert handler.agent.memory.cleared == 1
    assert handler.agent.memory.messages == []


def test_status_and_config_are_text_results(handler):
    status = handler.handle("/status")
    assert status.kind == TEXT
    assert status.payload["title"] == "Agent Status"
    assert "Emotion: normal" in status.payload["body"]

    config = handler.handle("/config")
    assert config.kind == TEXT
    assert config.payload["title"] == "Runtime Config"
    assert "Model: m" in config.payload["body"]


def test_remember_returns_agent_message(handler):
    result = handler.handle("/remember")
    assert result.kind == AFFIRM
    assert result.payload["message"] == "记忆已保存"
    assert handler.agent.remember_calls == 1


def test_history_table_shape_and_truncation():
    messages = [
        {"role": "user", "content": "a" * 300},
        {"role": "assistant", "content": "hi"},
        {"role": "tool", "tool_call_id": "call_1", "content": ""},
    ]
    handler = CommandHandler(FakeAgent(messages))
    result = handler.handle("/history 3")

    assert result.kind == TABLE
    assert result.payload["columns"] == ["#", "Role", "Content"]
    rows = result.payload["rows"]
    assert [row[0] for row in rows] == ["1", "2", "3"]
    assert rows[0][2].endswith("…") and len(rows[0][2]) == 201
    assert rows[1][1] == "assistant"
    assert rows[2][2] == "[tool_result] call_1"


def test_history_default_is_ten():
    messages = [{"role": "user", "content": str(i)} for i in range(15)]
    handler = CommandHandler(FakeAgent(messages))
    result = handler.handle("/history")
    assert len(result.payload["rows"]) == 10


def test_history_empty_and_invalid_argument(handler):
    assert handler.handle("/history") .payload["body"] == "暂无对话历史。"
    invalid = handler.handle("/history abc")
    assert invalid.kind == TEXT
    assert "请输入数字" in invalid.payload["body"]


def test_results_carry_no_rich_markup(handler):
    """结果不得含富文本标记：标记属于渲染层，且会污染纯文本输出。"""
    targets = ["/help", "/status", "/config", "/history", "/clear", "/happy", "/nope"]
    for command in targets:
        payload = json.dumps(handler.handle(command).payload, ensure_ascii=False)
        assert "[bold" not in payload, f"{command} 结果含富文本标记"
        assert "[green" not in payload, f"{command} 结果含富文本标记"
        assert "[dim" not in payload, f"{command} 结果含富文本标记"


# ── 纯文本渲染（Web / 无 rich 环境） ─────────────────────────────


def test_plain_renderer_handles_every_kind():
    assert command_format.render_command_result(CommandResult(TEXT, {"title": "T", "body": "B"})) == "T\nB"
    assert command_format.render_command_result(CommandResult(AFFIRM, {"message": "ok"})) == "ok"
    assert command_format.render_command_result(CommandResult(CONFIRMATION, {"message": "sure?"})) == "sure?"


def test_plain_renderer_table_alignment():
    result = CommandResult(
        TABLE,
        {"title": "T", "columns": ["A", "BB"], "rows": [["1", "2"], ["longer", "3"]]},
    )
    lines = command_format.render_command_result(result).splitlines()
    assert lines[0] == "T"
    assert lines[1] == "A       BB"
    assert set(lines[2]) <= {"-", " "}
    assert lines[3] == "1       2"
    assert lines[4] == "longer  3"


def test_plain_renderer_rejects_unknown_kind():
    with pytest.raises(ValueError):
        command_format.render_command_result(CommandResult("nonsense", {}))


def test_real_command_results_render_as_plain_text():
    """真实命令结果必须能被纯文本渲染器消化（Web 复用的前提）。"""
    handler = CommandHandler(FakeAgent([{"role": "user", "content": "hi"}]))
    for command in ["/help", "/status", "/config", "/history", "/nope"]:
        rendered = command_format.render_command_result(handler.handle(command))
        assert rendered.strip(), f"{command} 渲染为空"
