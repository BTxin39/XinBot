#!/usr/bin/env python3
"""同一个 MCP Server —— 用 MCP Python SDK 的 FastMCP + @mcp.tool 写法。

对比 scripts/mock_mcp_server.py（裸 JSON-RPC，200 行）:
  - 不需要手写 JSON-RPC 请求解析
  - 不需要手写 method 路由
  - 不需要手写 json.dumps / json.loads
  - 不需要理解 "id" "jsonrpc" "params" 这些协议字段

SDK 帮你处理了所有这些。你只写业务逻辑。

运行方式:
  python scripts/mcp_server_sdk_style.py
"""

from mcp.server.fastmcp import FastMCP

# ── 创建 FastMCP 实例 ──────────────────────────────────────────────

mcp = FastMCP("demo-server")


# ── 工具：用 @mcp.tool() 装饰器定义 ──────────────────────────────────
# 函数签名 → 自动生成 inputSchema
# docstring → 自动生成 description
# 类型注解 → 自动生成参数类型
# 返回值 → 自动包装为 {"content": [{"type":"text", "text":"..."}]}

@mcp.tool()
def echo(text: str) -> str:
    """回显输入的文本。可以用于验证 MCP 通信是否正常。"""
    return f"[echo] {text}"


@mcp.tool()
def add_numbers(a: float, b: float) -> str:
    """计算两个数字的和。演示有多个参数的工具。"""
    return f"{a} + {b} = {a + b}"


@mcp.tool()
def get_current_time() -> str:
    """获取服务器端的当前时间。"""
    from datetime import datetime
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# ── 启动 ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    mcp.run()
