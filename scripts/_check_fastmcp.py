from mcp.server.fastmcp import FastMCP

m = FastMCP("test")
print("FastMCP attrs:", [x for x in dir(m) if not x.startswith("_")])
print()

# Check if there's a tool decorator
if hasattr(m, "tool"):
    print("m.tool:", type(m.tool))
if hasattr(FastMCP, "tool"):
    print("FastMCP.tool:", type(FastMCP.tool))
