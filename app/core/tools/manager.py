import json

from app.core.tools.registry import ToolRegistry


class ToolManager:
    def __init__(self, registry: ToolRegistry):
        self.registry = registry

    def execute(self, tool_calls: list[dict]) -> list[dict]:
        results: list[dict] = []
        for tc in tool_calls:
            func = tc["function"]
            name = func["name"]
            arguments = json.loads(func.get("arguments", "{}"))
            tool = self.registry.get(name)
            if tool is None:
                content = f"Unknown tool: {name}"
            else:
                try:
                    content = tool.execute(**arguments)
                except Exception as e:
                    content = f"Tool '{name}' execution error: {e}"

            results.append(
                {
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": content,
                }
            )
        return results