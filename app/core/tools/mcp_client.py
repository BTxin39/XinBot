"""MCP (Model Context Protocol) 客户端。

通过 JSON-RPC 2.0 协议与 MCP Server 子进程通信，发现和调用远端工具。

协议层：
  传输层：stdio（stdin 发请求，stdout 读响应，stderr 是日志）
  编码：每行一个 JSON 对象（newline-delimited JSON）

支持三个核心方法：
  - initialize    → 握手，交换协议版本和能力
  - tools/list     → 发现远端工具
  - tools/call     → 调用远端工具

设计注意：
  - 每个 MCPClient 管理一个 MCP Server 子进程
  - 一个 Server 崩了不影响其他 Server
  - 子进程异步启动，设置超时防止 hang 住
"""

import json
import subprocess
import sys
import time
from dataclasses import dataclass, field


# ── 数据结构 ──────────────────────────────────────────────────────

@dataclass
class MCPToolDef:
    """MCP Server 返回的工具定义（传给 MCPToolWrapper）。"""
    name: str
    description: str
    inputSchema: dict  # JSON Schema 格式的参数定义


@dataclass
class MCPServerConfig:
    """MCP Server 的启动配置。

    示例:
        MCPServerConfig(
            command="python",
            args=["scripts/mock_mcp_server.py"],
        )
        MCPServerConfig(
            command="npx",
            args=["-y", "@anthropic/mcp-server-filesystem", "."],
        )
    """
    command: str
    args: list[str] = field(default_factory=list)

    def as_command_list(self) -> list[str]:
        """转为 subprocess.Popen 需要的列表格式。"""
        return [self.command] + self.args


# ── 错误类型 ──────────────────────────────────────────────────────

class MCPError(Exception):
    """MCP 协议层错误。"""
    pass


class MCPTimeoutError(MCPError):
    """MCP 请求超时。"""
    pass


class MCPConnectionError(MCPError):
    """MCP 连接断开（子进程崩溃）。"""
    pass


# ── MCP 客户端 ────────────────────────────────────────────────────

class MCPClient:
    """MCP JSON-RPC 客户端。

    使用方式：
        client = MCPClient(["python", "scripts/mock_mcp_server.py"])
        client.initialize()
        tools = client.list_tools()
        result = client.call_tool("echo", {"text": "hello"})
        client.close()
    """

    # 启动/握手超时（秒）
    STARTUP_TIMEOUT = 10

    def __init__(self, command_list: list[str]):
        """初始化客户端并启动 MCP Server 子进程。

        Args:
            command_list: 启动命令，如 ["python", "scripts/mock_mcp_server.py"]

        Raises:
            MCPConnectionError: 子进程无法启动或超时
        """
        self._command_list = command_list
        self._proc: subprocess.Popen | None = None
        self._req_id: int = 0
        self._start_server()

    # ── 生命周期 ──────────────────────────────────────────────

    def _start_server(self):
        """启动 MCP Server 子进程。"""
        try:
            self._proc = subprocess.Popen(
                self._command_list,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,  # server 日志走 stderr
                text=True,
            )
        except FileNotFoundError:
            raise MCPConnectionError(
                f"无法启动 MCP Server: 命令不存在 '{self._command_list[0]}'"
            )
        except OSError as e:
            raise MCPConnectionError(f"无法启动 MCP Server: {e}")

        # 检查子进程是否立即崩溃
        time.sleep(0.3)
        if self._proc.poll() is not None:
            stderr = self._proc.stderr.read() if self._proc.stderr else ""
            raise MCPConnectionError(
                f"MCP Server 启动后立即退出 (exit code={self._proc.returncode})\n"
                f"stderr: {stderr[:500]}"
            )

    def initialize(self) -> dict:
        """MCP 握手：发送 initialize 请求 + initialized 通知。

        Returns:
            Server 的 initialize 响应，包含 capabilities 和 serverInfo。

        Raises:
            MCPConnectionError: 握手失败
        """
        result = self._send_request("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "xinbot", "version": "0.1.0"},
        })

        # 握手完成后必须发 initialized 通知
        self._send_notification("notifications/initialized")

        return result

    def close(self):
        """关闭 MCP Server 子进程。"""
        if self._proc and self._proc.poll() is None:
            try:
                self._proc.stdin.close()
            except OSError:
                pass
            self._proc.terminate()
            try:
                self._proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._proc.kill()
                self._proc.wait()

    # ── 工具操作 ──────────────────────────────────────────────

    def list_tools(self) -> list[MCPToolDef]:
        """发现 MCP Server 提供的工具列表。

        Returns:
            MCPToolDef 列表。如果 Server 没有工具，返回空列表。

        Raises:
            MCPError: Server 返回错误
        """
        result = self._send_request("tools/list")
        tools_data = result.get("tools", [])
        return [
            MCPToolDef(
                name=t["name"],
                description=t.get("description", ""),
                inputSchema=t.get("inputSchema", {}),
            )
            for t in tools_data
        ]

    def call_tool(self, name: str, arguments: dict) -> str:
        """调用 MCP Server 上的工具。

        Args:
            name: 工具名
            arguments: 工具参数

        Returns:
            工具执行结果的文本内容。如果 Server 返回多段内容，
            用换行连接。

        Raises:
            MCPConnectionError: 子进程崩溃
            MCPError: Server 返回错误
        """
        result = self._send_request("tools/call", {
            "name": name,
            "arguments": arguments,
        })

        # MCP tools/call 响应格式：
        # {"content": [{"type": "text", "text": "..."}, ...]}
        contents = result.get("content", [])
        text_parts = []
        for item in contents:
            if item.get("type") == "text":
                text_parts.append(item.get("text", ""))

        return "\n".join(text_parts) if text_parts else json.dumps(result)

    # ── JSON-RPC 核心 ─────────────────────────────────────────

    def _next_id(self) -> int:
        """生成自增请求 ID。"""
        self._req_id += 1
        return self._req_id

    def _send_request(self, method: str, params: dict | None = None) -> dict:
        """发送一个 JSON-RPC 请求，等待并返回 result。

        Args:
            method: 方法名（如 "tools/list"）
            params: 方法参数

        Returns:
            响应中的 result 字段

        Raises:
            MCPConnectionError: 子进程退出
            MCPError: Server 返回的 JSON-RPC error
        """
        req_id = self._next_id()
        request = {
            "jsonrpc": "2.0",
            "id": req_id,
            "method": method,
            "params": params or {},
        }
        response = self._send_raw(request)

        if "error" in response:
            err = response["error"]
            raise MCPError(
                f"MCP Server 返回错误 (code={err.get('code')}): {err.get('message')}"
            )

        return response.get("result", {})

    def _send_notification(self, method: str, params: dict | None = None):
        """发送一个 JSON-RPC 通知（无 id，不等待响应）。"""
        notification = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params or {},
        }
        self._send_raw(notification, expect_response=False)

    def _send_raw(self, message: dict, expect_response: bool = True) -> dict | None:
        """发送原始 JSON-RPC 消息，可选是否等待响应。

        这是所有通信的底层实现。
        """
        if self._proc is None or self._proc.poll() is not None:
            raise MCPConnectionError("MCP Server 已退出")

        # 发送
        req_str = json.dumps(message, ensure_ascii=False)
        try:
            self._proc.stdin.write(req_str + "\n")
            self._proc.stdin.flush()
        except (BrokenPipeError, OSError) as e:
            raise MCPConnectionError(f"MCP Server 连接断开: {e}")

        if not expect_response:
            return None

        # 接收
        try:
            resp_line = self._proc.stdout.readline()
        except OSError as e:
            raise MCPConnectionError(f"MCP Server 读取响应失败: {e}")

        if not resp_line:
            # stdout 关闭 → 子进程退出了
            self._proc.wait()
            stderr = ""
            if self._proc.stderr:
                try:
                    stderr = self._proc.stderr.read()
                except OSError:
                    pass
            raise MCPConnectionError(
                f"MCP Server 意外退出 (exit code={self._proc.returncode})\n"
                f"stderr: {stderr[:500]}"
            )

        try:
            return json.loads(resp_line)
        except json.JSONDecodeError as e:
            raise MCPError(f"MCP Server 返回了无效 JSON: {resp_line[:200]}... ({e})")
