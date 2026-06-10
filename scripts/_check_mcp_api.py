"""Check MCP SDK API."""
from mcp.server import Server
from mcp.server import stdio

# Check Server API
server_attrs = [x for x in dir(Server) if not x.startswith("_")]
print("Server attrs:", server_attrs)

# Check decorator pattern
import inspect
if hasattr(Server, "list_tools"):
    print("Server has list_tools method")
    print(inspect.signature(Server.list_tools))

# Check for tool registration patterns
for name in server_attrs:
    attr = getattr(Server, name)
    if callable(attr) and "tool" in name.lower():
        try:
            print(f"{name}: {inspect.signature(attr)}")
        except:
            print(f"{name}: (no signature)")

# Check mcp package version
import mcp
print("mcp version:", getattr(mcp, "__version__", "unknown"))
