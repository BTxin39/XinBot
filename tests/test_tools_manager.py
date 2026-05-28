import pytest
from app.core.tools.manager import ToolManager
from app.core.tools.registry import ToolRegistry
from app.core.tools.base import BaseTool


class EchoTool(BaseTool):
    name = "echo"
    description = "Echo back the input"
    parameters = []

    def execute(self, **kwargs) -> str:
        return "echo"


class AddTool(BaseTool):
    name = "add"
    description = "Add two numbers"
    parameters = []

    def execute(self, a: int, b: int) -> str:
        return str(a + b)


class FailingTool(BaseTool):
    name = "failing"
    description = "Always fails"
    parameters = []

    def execute(self, **kwargs) -> str:
        raise RuntimeError("intentional failure")


class TestToolManager:
    def test_execute_single_tool(self):
        registry = ToolRegistry()
        registry.register(EchoTool())
        manager = ToolManager(registry)

        results = manager.execute(
            [
                {
                    "id": "call_1",
                    "function": {"name": "echo", "arguments": "{}"},
                }
            ]
        )

        assert len(results) == 1
        assert results[0]["role"] == "tool"
        assert results[0]["tool_call_id"] == "call_1"
        assert results[0]["content"] == "echo"

    def test_execute_tool_with_arguments(self):
        registry = ToolRegistry()
        registry.register(AddTool())
        manager = ToolManager(registry)

        results = manager.execute(
            [
                {
                    "id": "call_add",
                    "function": {"name": "add", "arguments": '{"a": 2, "b": 3}'},
                }
            ]
        )

        assert results[0]["content"] == "5"

    def test_execute_multiple_calls(self):
        registry = ToolRegistry()
        registry.register(EchoTool())
        manager = ToolManager(registry)

        results = manager.execute(
            [
                {"id": "c1", "function": {"name": "echo", "arguments": "{}"}},
                {"id": "c2", "function": {"name": "echo", "arguments": "{}"}},
            ]
        )

        assert len(results) == 2
        assert results[0]["tool_call_id"] == "c1"
        assert results[1]["tool_call_id"] == "c2"

    def test_unknown_tool_returns_error_message(self):
        registry = ToolRegistry()
        manager = ToolManager(registry)

        results = manager.execute(
            [
                {
                    "id": "call_x",
                    "function": {"name": "nonexistent", "arguments": "{}"},
                }
            ]
        )

        assert "Unknown tool" in results[0]["content"]

    def test_tool_execution_error_is_caught(self):
        registry = ToolRegistry()
        registry.register(FailingTool())
        manager = ToolManager(registry)

        results = manager.execute(
            [
                {
                    "id": "call_fail",
                    "function": {"name": "failing", "arguments": "{}"},
                }
            ]
        )

        assert "execution error" in results[0]["content"]
