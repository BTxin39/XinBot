import pytest
from app.core.tools.registry import ToolRegistry
from app.core.tools.base import BaseTool


class FakeTool(BaseTool):
    name = "fake"
    description = "A fake tool"
    parameters = []

    def execute(self, **kwargs) -> str:
        return "fake"


class AnotherTool(BaseTool):
    name = "another"
    description = "Another tool"
    parameters = []

    def execute(self, **kwargs) -> str:
        return "another"


class TestToolRegistry:
    def test_register_and_get(self):
        registry = ToolRegistry()
        tool = FakeTool()
        registry.register(tool)
        assert registry.get("fake") is tool

    def test_get_nonexistent_returns_none(self):
        registry = ToolRegistry()
        assert registry.get("nonexistent") is None

    def test_list_tools(self):
        registry = ToolRegistry()
        registry.register(FakeTool())
        registry.register(AnotherTool())
        assert len(registry.list_tools()) == 2
        names = {t.name for t in registry.list_tools()}
        assert names == {"fake", "another"}

    def test_get_tools_schema(self):
        registry = ToolRegistry()
        registry.register(FakeTool())
        registry.register(AnotherTool())
        schemas = registry.get_tools_schema()
        assert len(schemas) == 2
        names = [s["function"]["name"] for s in schemas]
        assert "fake" in names
        assert "another" in names

    def test_duplicate_registration_overwrites(self):
        registry = ToolRegistry()
        tool1 = FakeTool()
        tool2 = FakeTool()
        registry.register(tool1)
        registry.register(tool2)
        assert registry.get("fake") is tool2
        assert len(registry.list_tools()) == 1
