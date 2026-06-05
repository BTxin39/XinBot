#!/usr/bin/env python3
"""Mock MCP Server — 用于学习 MCP 协议和测试 MCPClient。

实现了一个最小但完整的 MCP Server，通过 stdin/stdout 用 JSON-RPC 2.0 通信。
支持三个方法：
  - initialize      → 握手
  - tools/list       → 列出可用工具
  - tools/call       → 调用工具

这个 server 提供了 2 个演示工具：
  - echo         : 回显输入的文本
  - add_numbers  : 对两个数字求和

启动方式（被 MCPClient 作为子进程启动）：
  python scripts/mock_mcp_server.py

JSON-RPC 2.0 协议概要：
  请求  → {"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}
  响应  → {"jsonrpc":"2.0","id":1,"result":{...}}
  错误  → {"jsonrpc":"2.0","id":1,"error":{"code":-32601,"message":"..."}}
  通知  → {"jsonrpc":"2.0","method":"notifications/initialized"}   ← 无 id，无响应
"""

import json
import sys


# ── 工具定义（MCP 返回的格式）─────────────────────────────────────
# 注意：MCP 的 inputSchema 是标准 JSON Schema，和 OpenAI 的格式很接近
# 但包装层次不同。MCPToolWrapper 负责转换。

MCP_TOOLS = [
    {
        "name": "echo",
        "description": "回显输入的文本。可以用于验证 MCP 通信是否正常。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": "要回显的文本",
                },
            },
            "required": ["text"],
        },
    },
    {
        "name": "add_numbers",
        "description": "计算两个数字的和。演示有多个参数的工具。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "a": {
                    "type": "number",
                    "description": "第一个数字",
                },
                "b": {
                    "type": "number",
                    "description": "第二个数字",
                },
            },
            "required": ["a", "b"],
        },
    },
]


# ── 方法处理器 ────────────────────────────────────────────────────

def handle_initialize(params: dict) -> dict:
    """握手：返回协议版本和服务端能力。"""
    return {
        "protocolVersion": "2024-11-05",
        "capabilities": {
            "tools": {},  # 声明支持工具调用
        },
        "serverInfo": {
            "name": "mock-mcp-server",
            "version": "0.1.0",
        },
    }


def handle_tools_list(params: dict) -> dict:
    """返回可用工具列表。"""
    return {"tools": MCP_TOOLS}


def handle_tools_call(params: dict) -> dict:
    """调用工具，返回结果。"""
    name = params.get("name", "")
    arguments = params.get("arguments", {})

    if name == "echo":
        text = arguments.get("text", "")
        return {
            "content": [
                {"type": "text", "text": f"[echo] {text}"}
            ]
        }

    elif name == "add_numbers":
        a = arguments.get("a", 0)
        b = arguments.get("b", 0)
        result = a + b
        return {
            "content": [
                {"type": "text", "text": f"{a} + {b} = {result}"}
            ]
        }

    else:
        raise ValueError(f"Unknown tool: {name}")


# ── 路由表 ────────────────────────────────────────────────────────

METHOD_HANDLERS = {
    "initialize": handle_initialize,
    "tools/list": handle_tools_list,
    "tools/call": handle_tools_call,
}


# ── 主循环：从 stdin 读请求，通过 stdout 写响应 ─────────────────

def main():
    # 关键：所有 MCP 通信走 stdin/stdout
    # stderr 留给日志（不要把日志写到 stdout，会破坏协议！）
    print("[mock_mcp_server] started, waiting for requests...", file=sys.stderr)

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue

        try:
            request = json.loads(line)
        except json.JSONDecodeError as e:
            print(f"[mock_mcp_server] invalid json: {e}", file=sys.stderr)
            continue

        method = request.get("method", "")
        req_id = request.get("id")
        params = request.get("params", {})

        # 通知（无 id）→ 处理但不响应
        # JSON-RPC 中，没有 id 的消息是通知/通知，不需要响应
        if req_id is None:
            print(
                f"[mock_mcp_server] notification: {method}",
                file=sys.stderr,
            )
            continue

        # 请求（有 id）→ 处理并返回响应
        handler = METHOD_HANDLERS.get(method)
        if handler is None:
            response = {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {
                    "code": -32601,
                    "message": f"Method not found: {method}",
                },
            }
        else:
            try:
                result = handler(params)
                response = {"jsonrpc": "2.0", "id": req_id, "result": result}
            except Exception as e:
                response = {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {"code": -32603, "message": str(e)},
                }

        # 每个响应一行 JSON，末尾加换行
        sys.stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
