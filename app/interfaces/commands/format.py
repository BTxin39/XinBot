"""命令结果的纯文本渲染 —— 供 Web 终端与任何无 rich 的调用方使用。

与 `app/interfaces/cli/command_render.py`（rich 渲染）共用同一份 `CommandResult` 契约，
避免两端各自拼字符串再次漂移。见 docs/DECISIONS_V0.2.md §6。
"""

from app.interfaces.commands.result import AFFIRM, CONFIRMATION, TABLE, TEXT, CommandResult


def _render_table(payload: dict) -> str:
    title = payload.get("title", "")
    columns = [str(column) for column in payload.get("columns", [])]
    rows = [[str(cell) for cell in row] for row in payload.get("rows", [])]
    if not columns:
        return title

    widths = [len(column) for column in columns]
    for row in rows:
        for index, cell in enumerate(row[: len(widths)]):
            widths[index] = max(widths[index], len(cell))

    def line(cells: list[str]) -> str:
        return "  ".join(cell.ljust(widths[index]) for index, cell in enumerate(cells)).rstrip()

    lines = []
    if title:
        lines.append(title)
    lines.append(line(columns))
    lines.append("  ".join("-" * width for width in widths))
    lines.extend(line(row) for row in rows)
    return "\n".join(lines)


def render_command_result(result: CommandResult) -> str:
    """把命令结果渲染为纯文本。"""
    if result.kind == TABLE:
        return _render_table(result.payload)
    if result.kind in (TEXT, CONFIRMATION, AFFIRM):
        payload = result.payload
        title = payload.get("title", "")
        body = payload.get("body") or payload.get("message", "")
        return f"{title}\n{body}" if title else body
    raise ValueError(f"未知的命令结果类型: {result.kind!r}")
