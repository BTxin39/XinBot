"""测试 MCP 客户端和工具包装器。

使用真实的 mock_mcp_server 子进程做集成测试，
确保 JSON-RPC 通信端到端正确。
"""

import pytest
from app.core.tools.mcp_client import (
    MCPClient,
    MCPToolDef,
    MCPError,
    MCPConnectionError,
)
from app.core.tools.mcp_wrapper import (
    MCPWrapperTool,
    _input_schema_to_params,
)
from app.core.tools.base import DangerLevel, BaseTool

# mock server 的启动命令
MOCK_SERVER_CMD = ["python", "scripts/mock_mcp_server.py"]


# ── fixture: 一个已初始化的 MCP 客户端 ───────────────────────────

@pytest.fixture
def mcp_client():
    """创建并初始化一个连接到 mock server 的 MCPClient。"""
    client = MCPClient(MOCK_SERVER_CMD)
    client.initialize()
    yield client
    client.close()


# ── MCPClient 测试 ────────────────────────────────────────────────

class TestMCPClient:
    def test_initialize_succeeds(self):
        """握手成功，返回 Server 信息。"""
        client = MCPClient(MOCK_SERVER_CMD)
        try:
            result = client.initialize()
            assert result["protocolVersion"] == "2024-11-05"
            assert "tools" in result["capabilities"]
            assert result["serverInfo"]["name"] == "mock-mcp-server"
        finally:
            client.close()

    def test_list_tools_returns_tools(self, mcp_client):
        """tools/list 返回正确的工具列表。"""
        tools = mcp_client.list_tools()

        assert len(tools) >= 2
        tool_names = {t.name for t in tools}
        assert "echo" in tool_names
        assert "add_numbers" in tool_names

    def test_list_tools_returns_mcp_tool_def(self, mcp_client):
        """返回的是 MCPToolDef 实例，属性正确。"""
        tools = mcp_client.list_tools()
        echo = [t for t in tools if t.name == "echo"][0]

        assert isinstance(echo, MCPToolDef)
        assert echo.name == "echo"
        assert "回显" in echo.description
        assert "properties" in echo.inputSchema

    def test_call_echo_tool(self, mcp_client):
        """调用 echo 工具，返回回显文本。"""
        result = mcp_client.call_tool("echo", {"text": "Hello MCP"})

        assert "Hello MCP" in result

    def test_call_add_numbers_tool(self, mcp_client):
        """调用 add_numbers，返回计算结果。"""
        result = mcp_client.call_tool("add_numbers", {"a": 10, "b": 32})

        assert "42" in result

    def test_call_unknown_tool_raises_error(self, mcp_client):
        """调用不存在的工具 → MCPError。"""
        with pytest.raises(MCPError):
            mcp_client.call_tool("no_such_tool", {})

    def test_connection_refused_raises_error(self):
        """连接到不存在的命令 → MCPConnectionError。"""
        with pytest.raises(MCPConnectionError):
            MCPClient(["python", "nonexistent_file_xyz.py"])


# ── MCPWrapperTool 测试 ───────────────────────────────────────────

class TestMCPWrapperTool:
    @pytest.fixture
    def echo_tool_def(self, mcp_client):
        """获取 echo 工具的 MCPToolDef。"""
        tools = mcp_client.list_tools()
        return [t for t in tools if t.name == "echo"][0]

    @pytest.fixture
    def add_tool_def(self, mcp_client):
        """获取 add_numbers 工具的 MCPToolDef。"""
        tools = mcp_client.list_tools()
        return [t for t in tools if t.name == "add_numbers"][0]

    def test_is_base_tool_subclass(self, echo_tool_def, mcp_client):
        """MCPWrapperTool 是 BaseTool 的子类。"""
        wrapper = MCPWrapperTool(echo_tool_def, mcp_client)
        assert isinstance(wrapper, BaseTool)

    def test_name_and_description(self, echo_tool_def, mcp_client):
        """工具名和描述被正确传递。"""
        wrapper = MCPWrapperTool(echo_tool_def, mcp_client)

        assert wrapper.name == "echo"
        assert "回显" in wrapper.description

    def test_parameters_from_input_schema(self, echo_tool_def, mcp_client):
        """inputSchema 正确转为 ToolParameter 列表。"""
        wrapper = MCPWrapperTool(echo_tool_def, mcp_client)

        assert len(wrapper.parameters) == 1
        param = wrapper.parameters[0]
        assert param.name == "text"
        assert param.type == "string"
        assert param.required is True

    def test_execute_delegates_to_client(self, echo_tool_def, mcp_client):
        """execute() 通过 MCPClient 调用远端工具。"""
        wrapper = MCPWrapperTool(echo_tool_def, mcp_client)

        result = wrapper.execute(text="test123")

        assert "test123" in result

    def test_execute_with_multiple_params(self, add_tool_def, mcp_client):
        """多参数工具调用。"""
        wrapper = MCPWrapperTool(add_tool_def, mcp_client)

        result = wrapper.execute(a=5, b=7)

        assert "12" in result

    def test_default_danger_level_is_readonly(self, echo_tool_def, mcp_client):
        """默认危险等级是 READ_ONLY（远端工具保守策略）。"""
        wrapper = MCPWrapperTool(echo_tool_def, mcp_client)

        assert wrapper.danger_level == DangerLevel.READ_ONLY

    def test_can_override_danger_level(self, echo_tool_def, mcp_client):
        """可以显式覆盖危险等级。"""
        wrapper = MCPWrapperTool(
            echo_tool_def, mcp_client,
            danger_level=DangerLevel.DANGEROUS,
        )

        assert wrapper.danger_level == DangerLevel.DANGEROUS

    def test_openai_schema_generation(self, echo_tool_def, mcp_client):
        """生成的 OpenAI schema 格式正确。"""
        wrapper = MCPWrapperTool(echo_tool_def, mcp_client)
        schema = wrapper.to_openai_schema()

        assert schema["type"] == "function"
        func = schema["function"]
        assert func["name"] == "echo"
        assert "properties" in func["parameters"]
        assert "text" in func["parameters"]["properties"]

    def test_client_error_returns_string(self, echo_tool_def, mcp_client):
        """MCP 通信错误时 execute() 返回错误字符串，不抛异常。

        模拟：关闭 MCPClient 后再调用工具 → 通信错误。
        """
        wrapper = MCPWrapperTool(echo_tool_def, mcp_client)
        mcp_client.close()

        result = wrapper.execute(text="test")

        # 不抛异常，返回错误描述
        assert isinstance(result, str)
        assert ("失败" in result or "异常" in result or "退出" in result)


# ── inputSchema 转换测试 ─────────────────────────────────────────

class TestInputSchemaConversion:
    def test_basic_conversion(self):
        """基本类型参数正确转换。"""
        schema = {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "用户名"},
                "age": {"type": "integer", "description": "年龄"},
                "active": {"type": "boolean", "description": "是否激活"},
            },
            "required": ["name"],
        }

        params = _input_schema_to_params(schema)

        assert len(params) == 3
        names = {p.name: p for p in params}

        assert names["name"].type == "string"
        assert names["name"].required is True
        assert names["age"].type == "integer"
        assert names["age"].required is False
        assert names["active"].type == "boolean"

    def test_empty_schema(self):
        """空 schema 返回空参数列表。"""
        params = _input_schema_to_params({})
        assert params == []

    def test_skips_unsupported_types(self):
        """跳过大模型不支持的复杂类型（array, object）。"""
        schema = {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "tags": {"type": "array"},
                "metadata": {"type": "object"},
            },
        }

        params = _input_schema_to_params(schema)

        # 只保留 string，跳过 array 和 object
        assert len(params) == 1
        assert params[0].name == "name"
