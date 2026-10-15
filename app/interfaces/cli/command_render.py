"""命令结果的 rich 渲染（CLI 专用）。

命令层返回结构化 `CommandResult` 后，终端呈现集中到这里，
使命令逻辑能被 Web 复用（见 docs/DECISIONS_V0.2.md §6）。
"""

from rich.console import Console
from rich.table import Table
from rich.text import Text

from app.interfaces.commands.result import AFFIRM, CONFIRMATION, TABLE, TEXT, CommandResult

# 与历史 CLI 输出保持一致的配色
KIND_STYLES = {
    TEXT: "white",
    AFFIRM: "green",
    CONFIRMATION: "yellow",
}

ROLE_STYLES = {
    "user": "bold yellow",
    "assistant": "bold green",
    "system": "dim",
    "tool": "magenta",
}


def render_command_result(result: CommandResult, console: Console | None = None) -> None:
    """把命令结果打印到终端。"""
    output = console or Console()

    if result.kind == TABLE:
        output.print(_build_table(result.payload))
        return

    if result.kind in (TEXT, AFFIRM, CONFIRMATION):
        payload = result.payload
        title = payload.get("title", "")
        body = payload.get("body") or payload.get("message", "")
        if title:
            output.print(f"[bold green]{title}[/bold green]")
        output.print(body, style=KIND_STYLES.get(result.kind, "white"))
        return

    raise ValueError(f"未知的命令结果类型: {result.kind!r}")


def _build_table(payload: dict) -> Table:
    table = Table(title=payload.get("title", ""), border_style="blue")
    columns = [str(name) for name in payload.get("columns", [])]
    for name in columns:
        table.add_column(name, style="bold cyan")

    # 历史表格的 Role 列沿用 role 配色（原实现把样式内联在富文本里）
    role_index = columns.index("Role") if "Role" in columns else None

    for row in payload.get("rows", []):
        cells: list[Text | str] = [str(cell) for cell in row]
        if role_index is not None and role_index < len(cells):
            role = str(cells[role_index])
            style = ROLE_STYLES.get(role)
            if style:
                cells[role_index] = Text(role, style=style)
        table.add_row(*cells)
    return table
