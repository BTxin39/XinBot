"""命令结果的数据结构 —— 命令层与渲染层之间的契约。

为什么要这一层（docs/DECISIONS/DECISIONS_V0.2.0.md §6）：
原 `app/interfaces/commands/handler.py` 直接 `rich.console.print`，导致同一套命令逻辑
无法被 Web 复用（Web 只能在 `app/interfaces/web/routes/memory.py` 里另写一套手搓 parser）。

现在命令层只返回结构化结果，渲染由各适配器负责：
    - CLI：`app/interfaces/cli/command_render.py` 用 rich 渲染
    - Web / 纯文本：`app/interfaces/commands/format.py` 渲染为字符串

`kind` 与 `payload` 约定（保持稳定，新增 kind 需同时更新两个渲染器）：

| kind           | payload                            | CLI 表现         |
|----------------|------------------------------------|------------------|
| `text`         | `{"title": str, "body": str}`      | 面板内的多行文本  |
| `table`        | `{"title": str, "columns": [...], "rows": [[...]]}` | rich 表格 |
| `confirmation` | `{"message": str}`                 | 黄色提示          |
| `affirm`       | `{"message": str}`                 | 绿色确认          |

注意：结果里**不得**出现 rich 标记（如 `[bold]`）—— 标记属于渲染层，
且历史实现存在把 role 名当富文本样式输出到文本渲染器的问题。
"""

from dataclasses import dataclass, field

TEXT = "text"
TABLE = "table"
CONFIRMATION = "confirmation"
AFFIRM = "affirm"

KINDS = (TEXT, TABLE, CONFIRMATION, AFFIRM)


@dataclass(frozen=True)
class CommandResult:
    """一条命令的执行结果。"""

    kind: str
    payload: dict = field(default_factory=dict)


def text(body: str, title: str = "") -> CommandResult:
    return CommandResult(TEXT, {"title": title, "body": body})


def table(title: str, columns: list[str], rows: list[list[str]]) -> CommandResult:
    return CommandResult(TABLE, {"title": title, "columns": list(columns), "rows": [list(row) for row in rows]})


def confirmation(message: str) -> CommandResult:
    return CommandResult(CONFIRMATION, {"message": message})


def affirm(message: str) -> CommandResult:
    return CommandResult(AFFIRM, {"message": message})
