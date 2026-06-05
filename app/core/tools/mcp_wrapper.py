"""MCP 工具包装器。

将 MCP Server 返回的远端工具包装成 BaseTool 子类，使其能被
ToolRegistry 注册、ToolManager 调度、ToolGuard 审批。

对 ToolManager 和 Agent 来说，MCPWrapperTool 就是一个普通的 BaseTool。
它不关心工具是本地的还是远端的——这是面向接口编程的价值。

关键转换：MCP inputSchema → ToolParameter 列表
  MCP:  {"type":"object", "properties":{"x":{"type":"string"}}, "required":["x"]}
  → ToolParameter(name="x", type="string", required=True)
  → OpenAI schema（由 BaseTool.to_openai_schema() 自动生成）

安全设计：
  远端工具默认 danger_level=READ_ONLY，因为客户端无法验证它们的行为。
  如果某个 MCP 工具有写操作，应该在配置中显式指定为 DANGEROUS。
"""

from app.core.tools.base import BaseTool, DangerLevel, ToolParameter
from app.core.tools.mcp_client import MCPClient, MCPError

# OpenAI Function Calling 支持的 JSON Schema 类型
SUPPORTED_TYPES = {"string", "number", "integer", "boolean"}


def _input_schema_to_params(schema: dict) -> list[ToolParameter]:
    """将 MCP 的 JSON Schema 参数定义转为 ToolParameter 列表。

    Args:
        schema: MCP 工具的 inputSchema，格式如：
            {"type":"object", "properties":{...}, "required":["..."]}

    Returns:
        ToolParameter 列表
    """
    params: list[ToolParameter] = []
    properties = schema.get("properties", {})
    required_list = schema.get("required", [])

    for name, prop in properties.items():
        param_type = prop.get("type", "string")
        # 跳过不支持的复杂类型
        if param_type not in SUPPORTED_TYPES:
            continue

        params.append(
            ToolParameter(
                name=name,
                type=param_type,
                description=prop.get("description", ""),
                required=name in required_list,
            )
        )

    return params


class MCPWrapperTool(BaseTool):
    """MCP 远端工具的本地代理。

    使用方式：
        tool_def = client.list_tools()[0]
        wrapper = MCPWrapperTool(tool_def, client)
        result = wrapper.execute(text="hello")  # 远端调用
    """

    def __init__(
        self,
        tool_def,
        mcp_client: MCPClient,
        danger_level: DangerLevel = DangerLevel.READ_ONLY,
    ):
        """包装一个 MCP 远端工具。

        Args:
            tool_def: MCPToolDef 实例（来自 MCPClient.list_tools()）
            mcp_client: 与提供此工具的 MCP Server 通信的客户端
            danger_level: 危险等级。远端工具默认 READ_ONLY，
                          更安全。如果需要写操作，注册时显式指定。
        """
        self.name = tool_def.name
        self.description = tool_def.description
        self.parameters = _input_schema_to_params(tool_def.inputSchema)
        self.danger_level = danger_level
        self._client = mcp_client

    def execute(self, **kwargs) -> str:
        """通过 MCPClient 调用远端工具。

        Args:
            **kwargs: 参数由 LLM 传入，与 ToolParameter.name 对应

        Returns:
            远端工具的执行结果

        异常处理：
            通信错误 → 返回错误描述字符串（不抛异常，遵循 BaseTool 约定）
        """
        try:
            return self._client.call_tool(self.name, kwargs)
        except MCPError as e:
            # 远端错误 → 返回字符串，LLM 可以据此调整行为
            return f"MCP 工具 '{self.name}' 调用失败: {e}"
        except Exception as e:
            return f"MCP 工具 '{self.name}' 异常: {e}"
