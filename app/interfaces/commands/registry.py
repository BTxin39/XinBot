"""斜杠命令注册与执行 —— **不含任何渲染依赖**。

历史问题（docs/DECISIONS/DECISIONS_V0.2.0.md §2.4、§6）：本模块原在 `app/interfaces/commands/handler.py`，
198 行里全是 `rich.console.print` / `rich.Table`，导致：
    1. Web 无法复用，只能在 `app/interfaces/web/routes/memory.py` 另写一套手搓 parser；
    2. 命令逻辑与终端呈现耦合，换个前端就得改命令层。

现在本模块只做解析与执行，返回 `CommandResult`：
    - CLI 渲染：`app/interfaces/cli/command_render.py`
    - 纯文本渲染：`app/interfaces/commands/format.py`

依赖纪律：本模块不得 import `rich`（由 `tests/test_layering.py` 的 R5 强制）。
"""

from dataclasses import dataclass
from typing import Callable

from app.interfaces.commands.result import CommandResult, affirm, table, text
from app.core.agent import Agent

# 历史实现把 role 名当富文本样式直接输出，这里改为纯文本展示名
ROLE_LABELS = {
    "user": "user",
    "assistant": "assistant",
    "system": "system",
    "tool": "tool",
}

HISTORY_DEFAULT_COUNT = 10
HISTORY_CONTENT_LIMIT = 200


@dataclass(frozen=True)
class Command:
    name: str
    help_description: str
    handler: Callable[..., CommandResult]
    accepts_arg: bool = False


class CommandHandler:
    """斜杠命令分派器（`CommandDispatcher` 协议的实现）。

    满足 `app/services/session.py` 的协议：
        handle(user_input) -> CommandResult | None
    返回 None 表示"不是命令"，应交给 LLM。
    """

    def __init__(self, agent: Agent):
        self.agent = agent
        self.handlers: dict[str, Command] = {}
        self.add_handlers()

    def add_handlers(self):
        """注册所有可用的命令处理器。"""
        self.handlers["help"] = Command("help", "Show available commands", self._help)
        self.handlers["clear"] = Command("clear", "Clear agent memory", self._clear_memory)
        self.handlers["config"] = Command("config", "Show runtime configuration", self._show_config)
        self.handlers["status"] = Command("status", "Show agent status", self._show_status)
        self.handlers["remember"] = Command(
            "remember", "Extract long-term memory from current conversation", self._remember_now
        )
        self.handlers["history"] = Command(
            "history", "Show N recent messages (e.g. /history 10)", self._show_history, accepts_arg=True
        )
        for emotion in ("happy", "sad", "angry", "sleepy", "normal"):
            self.handlers[emotion] = Command(
                emotion,
                f"Change emotion to {emotion}",
                # 默认参数绑定循环变量，避免闭包捕获最后一个值
                lambda emotion=emotion: self._change_emotion(emotion),
            )

    def handle(self, user_input: str) -> CommandResult | None:
        """执行命令；不是命令时返回 None。"""
        if not user_input.startswith("/"):
            return None

        parts = user_input[1:].split(maxsplit=1)
        command_name = parts[0]
        argument = parts[1] if len(parts) > 1 else ""

        command = self.handlers.get(command_name)
        if command is None:
            return CommandResult(
                "text",
                {"title": "UNKNOWN COMMAND", "body": self._help_text()},
            )

        if command.accepts_arg:
            return command.handler(argument)
        return command.handler()

    # ── 各命令实现 ───────────────────────────────────────────

    def help_entries(self) -> list[list[str]]:
        """命令清单（表格行），供 CLI / Web 共用。"""
        return [[f"/{cmd.name}", cmd.help_description] for cmd in self.handlers.values()]

    def _help_text(self) -> str:
        return "\n".join(f"/{cmd.name} - {cmd.help_description}" for cmd in self.handlers.values())

    def _help(self) -> CommandResult:
        return table("Commands", ["Command", "Description"], self.help_entries())

    def _clear_memory(self) -> CommandResult:
        self.agent.memory.clear()
        return affirm("Memory cleared")

    def _change_emotion(self, emotion: str) -> CommandResult:
        self.agent.change_emotion(emotion)
        return affirm(f"Emotion -> {emotion}")

    def _show_config(self) -> CommandResult:
        config = self.agent.config
        body = (
            f"Model: {config.model_name}\n"
            f"Provider: {config.provider}\n"
            f"Temperature: {config.temperature}\n"
            f"Memory Limit: {config.max_memory_messages}"
        )
        return text(body, title="Runtime Config")

    def _remember_now(self) -> CommandResult:
        return affirm(self.agent.remember_now())

    def _show_status(self) -> CommandResult:
        status = self.agent.get_status()
        body = (
            f"Emotion: {status.emotion}\n"
            f"Provider: {status.provider}\n"
            f"Model: {status.model_name}\n"
            f"Memory Messages: {status.memory_messages}"
        )
        return text(body, title="Agent Status")

    def _show_history(self, arg: str = "") -> CommandResult:
        """显示最近 N 条对话历史。

        /history     → 默认 10 条
        /history 5   → 最近 5 条
        """
        try:
            count = int(arg) if arg else HISTORY_DEFAULT_COUNT
        except ValueError:
            return text(f"无效参数: {arg}，请输入数字", title="参数错误")

        messages = self.agent.memory.get_message()
        if not messages:
            return text("暂无对话历史。")

        recent = messages[-count:]
        total = len(messages)
        rows = []
        for offset, message in enumerate(recent):
            index = total - len(recent) + offset + 1
            content = message.get("content", "")
            display = content[:HISTORY_CONTENT_LIMIT] + "…" if len(content) > HISTORY_CONTENT_LIMIT else content
            if not display:
                if message.get("tool_calls"):
                    display = "[tool_calls]"
                elif message.get("tool_call_id"):
                    display = f"[tool_result] {message.get('tool_call_id', '')}"
            role = ROLE_LABELS.get(message.get("role", ""), message.get("role", "?"))
            rows.append([str(index), role, display])

        return table(f"最近 {len(recent)} 条对话", ["#", "Role", "Content"], rows)
