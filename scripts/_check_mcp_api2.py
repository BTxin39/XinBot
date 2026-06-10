"""Check MCP SDK tool registration API."""
from mcp.server import Server
from mcp.server.stdio import stdio_server
import mcp

# Check if there's a FastMCP or similar
print("mcp package:", mcp.__file__)
print()

# Check for tool decorator in server module
import mcp.server
server_attrs = dir(mcp.server)
for name in server_attrs:
    if "tool" in name.lower() or "Tool" in name:
        print(f"mcp.server.{name}")

# Look for decorator/registration patterns
# Check if there's a tools module
try:
    from mcp.server import tools as server_tools
    print("mcp.server.tools:", [x for x in dir(server_tools) if not x.startswith("_")])
except ImportError:
    print("No mcp.server.tools")

# Check all of mcp for tool-related classes
import pkgutil
import os
mcp_path = os.path.dirname(mcp.__file__)
for root, dirs, files in os.walk(mcp_path):
    for f in files:
        if f.endswith('.py') and 'tool' in f.lower():
            print(os.path.join(root, f))
