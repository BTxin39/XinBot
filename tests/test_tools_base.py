import pytest
from app.core.tools.base import BaseTool, ToolParameter


class NoParamTool(BaseTool):
    name = "noop"
    description = "A tool with no parameters"
    parameters = []

    def execute(self, **kwargs) -> str:
        return "noop done"


class WithParamTool(BaseTool):
    name = "greet"
    description = "Greet someone"
    parameters = [
        ToolParameter(name="name", type="string", description="Who to greet"),
    ]

    def execute(self, name: str) -> str:
        return f"Hello, {name}"


class WithEnumTool(BaseTool):
    name = "set_mode"
    description = "Set a mode"
    parameters = [
        ToolParameter(
            name="mode",
            type="string",
            description="The mode to set",
            enum=["auto", "manual"],
        ),
    ]

    def execute(self, mode: str) -> str:
        return f"Mode: {mode}"


class TestBaseToolSchema:
    def test_no_params_schema(self):
        tool = NoParamTool()
        schema = tool.to_openai_schema()

        assert schema["type"] == "function"
        assert schema["function"]["name"] == "noop"
        assert schema["function"]["description"] == "A tool with no parameters"
        assert schema["function"]["parameters"]["type"] == "object"
        assert schema["function"]["parameters"]["properties"] == {}
        assert schema["function"]["parameters"]["required"] == []

    def test_with_params_schema(self):
        tool = WithParamTool()
        schema = tool.to_openai_schema()

        props = schema["function"]["parameters"]["properties"]
        assert "name" in props
        assert props["name"]["type"] == "string"
        assert props["name"]["description"] == "Who to greet"
        assert "enum" not in props["name"]

        required = schema["function"]["parameters"]["required"]
        assert "name" in required

    def test_enum_param_includes_enum_in_schema(self):
        tool = WithEnumTool()
        schema = tool.to_openai_schema()

        props = schema["function"]["parameters"]["properties"]
        assert props["mode"]["enum"] == ["auto", "manual"]

    def test_optional_param_not_in_required(self):
        class ToolWithOptional(BaseTool):
            name = "opt_tool"
            description = "Has optional param"
            parameters = [
                ToolParameter(
                    name="flag",
                    type="boolean",
                    description="A flag",
                    required=False,
                ),
            ]

            def execute(self, flag: bool = False) -> str:
                return str(flag)

        tool = ToolWithOptional()
        schema = tool.to_openai_schema()
        assert schema["function"]["parameters"]["required"] == []
