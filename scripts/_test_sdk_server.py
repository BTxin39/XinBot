"""测试 MCPClient 连接 SDK 风格的 MCP Server。"""
from app.core.tools.mcp_client import MCPClient

c = MCPClient(["python", "scripts/mcp_server_sdk_style.py"])
c.initialize()
tools = c.list_tools()
print("tools:", [t.name for t in tools])
r = c.call_tool("echo", {"text": "hello from sdk"})
print("echo result:", r)
r2 = c.call_tool("add_numbers", {"a": 10, "b": 20})
print("add result:", r2)
c.close()
print("done")
