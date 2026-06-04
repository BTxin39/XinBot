"""工具执行管理器。

职责：接收 LLM 返回的 tool_calls，逐个执行，返回 tool result 消息列表。

这是 Agent Loop 中 "Act" 步骤的实现。

数据流：
  LLM 返回 tool_calls（list[dict]）
    ↓
  ToolManager.execute(tool_calls)
    ├── 1. 遍历每个 tool_call
    ├── 2. 从 JSON 解析 arguments
    ├── 3. 从 registry 查找工具（找不到 → 返回错误消息）
    ├── 4. 🆕 guard.check(tool, kwargs)  ← 安全审批拦截点
    ├── 5. tool.execute(**kwargs)       ← 实际执行
    └── 6. 组装 {"role": "tool", ...} 格式的消息
    ↓
  返回 tool result 消息列表 → 添加到 memory → 下次 LLM 请求携带

异常处理策略：
  - 每个工具独立执行，一个失败不影响其他工具
  - 异常被捕获并转为 content 字符串，而不是让整个 Agent 崩溃
  - 这样 LLM 能读到 "Tool 'xxx' execution error: ..." 并调整行为

与 ToolGuard 的关系：
  ToolManager 负责"调度"（找到工具、解析参数、执行、组装结果）
  ToolGuard 负责"安检"（这个工具现在能执行吗？）
  两者解耦——换一种审批策略（CLI 询问 vs GUI 弹窗 vs 自动化测试）
  不需要动 ToolManager 的代码。
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from app.core.tools.registry import ToolRegistry

if TYPE_CHECKING:
    from app.core.tools.guard import ToolGuard


class ToolManager:
    def __init__(self, registry: ToolRegistry, guard: ToolGuard | None = None):
        """初始化工具管理器。

        Args:
            registry: 工具注册中心。ToolManager 只通过它查工具，不感知具体实现。
            guard: 安全审批守卫。None 时所有工具直接放行（测试/向后兼容）。
                   传入后，DANGEROUS 工具需审批，SAFE/READ_ONLY 直接放行。
        """
        self.registry = registry
        self._guard = guard

    def execute(self, tool_calls: list[dict]) -> list[dict]:
        """执行一批工具调用。

        每个 tool_call 的格式（来自 LLM）：
        {
            "id": "call_00_abc123",
            "type": "function",
            "function": {
                "name": "get_time",
                "arguments": "{}"
            }
        }

        返回格式（返回给 LLM 的 tool role 消息）：
        {
            "role": "tool",
            "tool_call_id": "call_00_abc123",
            "content": "2026-06-04 15:30:00"
        }

        Args:
            tool_calls: LLM 返回的 tool_calls 列表

        Returns:
            tool result 消息列表，每个元素对应一个 tool_call。
            可以直接传给 memory.add_message(**result)。
        """
        results: list[dict] = []
        for tc in tool_calls:
            # 1. 提取工具名和参数
            func = tc["function"]
            name = func["name"]
            # LLM 返回的 arguments 是 JSON 字符串，需要解析成 dict
            arguments = json.loads(func.get("arguments", "{}"))

            # 2. 从注册中心查找工具
            tool = self.registry.get(name)
            if tool is None:
                # 找不到工具：返回错误消息，但不崩溃
                # LLM 会读到 "Unknown tool" 并调整后续行为
                content = f"Unknown tool: {name}"
            else:
                # 3. 安全审批
                if self._guard is not None and not self._guard.check(tool, arguments):
                    content = f"Tool '{name}' execution denied by user."
                else:
                    # 4. 执行工具
                    try:
                        content = tool.execute(**arguments)
                    except Exception as e:
                        content = f"Tool '{name}' execution error: {e}"

            # 5. 组装 OpenAI 格式的 tool result 消息
            results.append(
                {
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": content,
                }
            )
        return results
