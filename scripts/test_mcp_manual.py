#!/usr/bin/env python3
"""手动测试 MCP JSON-RPC 通信。

这个脚本手动启动 mock_mcp_server 子进程，然后逐个发送 JSON-RPC 请求。
每一步都打印发送和接收的完整 JSON —— 让你看到协议的全貌。

运行方式：
  python scripts/test_mcp_manual.py
"""

import subprocess
import json
import sys
import time


def send_request(proc, method: str, params: dict | None = None, req_id: int = 1) -> dict:
    """发送一个 JSON-RPC 请求，返回响应。

    JSON-RPC 请求格式：
      {"jsonrpc":"2.0","id":<id>,"method":"<method>","params":{...}}

    响应格式：
      成功 → {"jsonrpc":"2.0","id":<id>,"result":{...}}
      失败 → {"jsonrpc":"2.0","id":<id>,"error":{"code":...,"message":"..."}}
    """
    request = {
        "jsonrpc": "2.0",
        "id": req_id,
        "method": method,
        "params": params or {},
    }

    # 发送：一行 JSON + 换行
    req_str = json.dumps(request, ensure_ascii=False)
    print(f"\n{'='*60}")
    print(f">>> 发送请求 (method={method}):")
    print(f"    {req_str}")

    proc.stdin.write(req_str + "\n")
    proc.stdin.flush()

    # 接收：读一行 JSON
    resp_str = proc.stdout.readline()
    response = json.loads(resp_str)

    print(f"<<< 收到响应:")
    print(f"    {json.dumps(response, ensure_ascii=False, indent=2)}")

    return response


def send_notification(proc, method: str, params: dict | None = None):
    """发送一个 JSON-RPC 通知（无 id，不期望响应）。"""
    notification = {
        "jsonrpc": "2.0",
        "method": method,
        "params": params or {},
    }

    req_str = json.dumps(notification, ensure_ascii=False)
    print(f"\n>>> 发送通知 (method={method}, 无id):")
    print(f"    {req_str}")

    proc.stdin.write(req_str + "\n")
    proc.stdin.flush()
    # 通知不等待响应！


def main():
    print("=" * 60)
    print("MCP JSON-RPC 手动通信测试")
    print("=" * 60)

    # 1. 启动 MCP Server 子进程
    print("\n[1] 启动 mock_mcp_server 子进程...")
    proc = subprocess.Popen(
        ["python", "scripts/mock_mcp_server.py"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,  # server 日志走 stderr，不影响协议
        text=True,
    )
    time.sleep(0.5)  # 等子进程就绪

    # 2. 握手：initialize
    print("\n[2] 握手...")
    send_request(proc, "initialize", params={
        "protocolVersion": "2024-11-05",
        "capabilities": {},
        "clientInfo": {"name": "xinbot", "version": "0.1.0"},
    })
    # 握手完成后必须发 initialized 通知
    send_notification(proc, "notifications/initialized")

    # 3. 发现工具：tools/list
    print("\n[3] 发现工具...")
    resp = send_request(proc, "tools/list", req_id=2)
    tools = resp.get("result", {}).get("tools", [])
    print(f"\n    → 发现了 {len(tools)} 个工具:")
    for tool in tools:
        print(f"      - {tool['name']}: {tool['description']}")

    # 4. 调用工具：tools/call (echo)
    print("\n[4] 调用 echo 工具...")
    send_request(proc, "tools/call", params={
        "name": "echo",
        "arguments": {"text": "Hello, MCP!"},
    }, req_id=3)

    # 5. 调用工具：tools/call (add_numbers)
    print("\n[5] 调用 add_numbers 工具...")
    send_request(proc, "tools/call", params={
        "name": "add_numbers",
        "arguments": {"a": 42, "b": 58},
    }, req_id=4)

    # 6. 错误处理：调用不存在的工具
    print("\n[6] 调用不存在的工具（期望错误）...")
    send_request(proc, "tools/call", params={
        "name": "nonexistent_tool",
        "arguments": {},
    }, req_id=5)

    # 7. 清理
    print("\n[7] 关闭子进程...")
    proc.stdin.close()
    proc.terminate()
    proc.wait()

    # 打印 server 的日志（stderr）
    stderr_output = proc.stderr.read()
    if stderr_output:
        print(f"\n[mock_mcp_server 日志]\n{stderr_output}")

    print("\n✅ 测试完成")


if __name__ == "__main__":
    main()
