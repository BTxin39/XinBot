"""终端审批交互 —— DANGEROUS 工具执行前询问用户。

设计依据见 `docs/DECISIONS_V0.2.md` §9：审批方式属于**交互层**职责，
core 只声明 `ApprovalCallback` 契约，由调用方注入具体实现。

- CLI：`Agent(config, approval_callback=cli_approval_callback)`
- Web：`Agent(config)` → 无回调 → `ToolGuard` 按 fail-safe 拒绝
- 测试：`Agent(config, approval_callback=lambda tool, kwargs: True)`
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # 仅用于类型标注，避免 core ↔ cli 的导入环
    from app.core.tools.base import BaseTool


def _truncate(text: str, max_len: int = 200) -> str:
    """截断长字符串，避免终端显示被大段 content 刷屏。"""
    if len(text) <= max_len:
        return text
    return text[:max_len] + f"…（共 {len(text)} 字符）"


def cli_approval_callback(tool: "BaseTool", kwargs: dict) -> bool:
    """CLI 环境下的审批交互。

    在终端显示危险操作警告和参数，等用户输入 y/N 决定。

    设计注意：这里不用 rich.Panel，因为回调可能在 Live/streaming
    上下文中被调用，rich 的复杂渲染会与 Live 刷新冲突导致显示截断。
    用纯 print() 在任何上下文中都可靠。
    """
    # 格式化参数显示（content 等长字符串要截断）
    param_lines = []
    for key, value in kwargs.items():
        displayed = _truncate(str(value))
        param_lines.append(f"  {key} = {displayed}")

    separator = "─" * 50

    print()  # 空行，与上方输出拉开距离
    print(separator)
    print(f"  ⚠️  危险操作: {tool.name}")
    print(f"  {tool.description}")
    print(f"  参数:")
    for line in param_lines:
        print(line)
    print(separator)
    print("  允许执行？[y/N]", end=" ", flush=True)

    answer = input("").strip().lower()
    return answer in ("y", "yes")
