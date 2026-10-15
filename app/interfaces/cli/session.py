"""终端会话装配：把命令层与 rich 渲染接到 `app.services.session.SessionRunner`。

为什么需要这一层：`services` 不得 import 命令适配器（依赖纪律 R2b），
"命令分派器用哪个实现、结果怎么渲染"必须由 CLI 侧决定。
见 docs/DECISIONS_V0.2.md §6。

本文件是**装配点**，因此允许 import 命令层与 rich（R2b 只约束 services）。
"""

from rich.console import Console

from app.interfaces.cli.command_render import render_command_result
from app.interfaces.commands.registry import CommandHandler
from app.services.session import SessionRunner, create_runner


def runner_factory(
    config,
    approval_callback=None,
    console: Console | None = None,
) -> SessionRunner:
    """构造带斜杠命令支持的终端会话（`xinbot start cli` / `xinbot debug`）。"""
    output = console or Console()
    return create_runner(
        config,
        dispatcher_factory=CommandHandler,
        approval_callback=approval_callback,
        on_command_result=lambda result: render_command_result(result, output),
    )


__all__ = ["CommandHandler", "render_command_result", "runner_factory"]
