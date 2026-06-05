#!/usr/bin/env python3
"""同一个 MCP Server —— 用 MCP Python SDK 的 @mcp.tool 写法。

对比 scripts/mock_mcp_server.py（裸 JSON-RPC，200 行）:
  - 不需要手写 JSON-RPC 请求解析
  - 不需要手写 method 路由
  - 不需要手写 json.dumps / json.loads
  - 不需要理解 "id" "jsonrpc" "params" 这些协议字段

SDK 帮你处理了所有这些。你只写业务逻辑。

安装（需要在 Windows 上额外处理 pywin32）:
  pip install mcp
  # 如果 pywin32 有问题:
  pip install pywin32
  python -c "import pywin32; print('ok')"

运行方式:
  python scripts/mcp_server_sdk_style.py
  # 或者通过 MCP 工具启动:
  # mcp dev scripts/mcp_server_sdk_style.py
"""

from mcp.server import Server
from mcp.server.stdio import stdio_server


# ── 创建 Server ───────────────────────────────────────────────────

server = Server("demo-server")


# ── 工具：用 @server.tool() 装饰器定义 ────────────────────────────
# 注意：这些装饰器会自动生成 JSON Schema，自动处理路由。
# 你写的函数签名 = 工具的 inputSchema
# 你写的 docstring = 工具的 description
# 你写的类型注解 = 参数类型

@server.tool()
def echo(text: str) -> str:
    """回显输入的文本。可以用于验证 MCP 通信是否正常。"""
    return f"[echo] {text}"


@server.tool()
def add_numbers(a: float, b: float) -> str:
    """计算两个数字的和。演示有多个参数的工具。"""
    return f"{a} + {b} = {a + b}"


@server.tool()
def get_current_time() -> str:
    """获取服务器端的当前时间。"""
    from datetime import datetime
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# ── 启动 ──────────────────────────────────────────────────────────
# 一行代码启动 stdio 传输。SDK 处理所有 JSON-RPC 细节。

if __name__ == "__main__":
    import asyncio
    async def main():
        async with stdio_server() as (read_stream, write_stream):
            await server.run(read_stream, write_stream, server.create_initialization_options())
    asyncio.run(main())
