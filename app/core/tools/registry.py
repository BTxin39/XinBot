"""工具注册中心。

这是工具系统的"电话簿"——按名字查找工具。设计非常克制：
- 只负责存储和查询，不参与执行、不参与审批
- 这是一个典型的 Registry 模式（也叫 Service Locator）

为什么不用自动发现？
  有的框架会扫描文件系统自动注册（"convention over configuration"），
  但这里选择手动注册。原因：
  1. 显式优于隐式：看 agent.py 的 _register_builtin_tools() 就知道有哪些工具
  2. 控制注册顺序：工具如果有依赖关系，手动注册能保证顺序
  3. 避免魔法：新人读代码不需要理解"为什么加个文件工具就自动生效了"
  4. 安全性：自动扫描可能意外注册测试工具或危险工具

如果以后工具数量暴增（50+），可以考虑按类别分 Registry 或引入装饰器注册，
但当前手动注册足够清晰。
"""

from app.core.tools.base import BaseTool


class ToolRegistry:
    def __init__(self):
        # dict 的实现选择：
        # 底层数据结构是 dict，不是 list。name → tool 的 O(1) 查找。
        # LLM 返回 tool_calls 时只给 name，我们需要快速找到对应的 tool 实例。
        # 如果遍历 list 查找，10 个工具就需要 10 次比较。
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        """注册一个工具。同名工具后注册的会覆盖先注册的。

        Args:
            tool: BaseTool 的子类实例。注册后可通过 tool.name 查询。

        调用时机：
        - Agent 初始化时，在 _register_builtin_tools() 中调用
        - 以后加载 MCP 远端的工具时，也会走这个入口
        """
        self._tools[tool.name] = tool

    def get(self, name: str) -> BaseTool | None:
        """按名称查找工具。找不到返回 None（ToolManager 负责处理 None 的情况）。

        Args:
            name: 工具名。对应 LLM tool_calls 中的 function.name。

        Returns:
            BaseTool 实例或 None。
        """
        return self._tools.get(name)

    def list_tools(self) -> list[BaseTool]:
        """返回所有已注册的工具实例列表。用于调试和状态展示。"""
        return list(self._tools.values())

    def get_tools_schema(self) -> list[dict]:
        """生成所有工具的 OpenAI schema 列表。

        这个方法在每次 LLM 请求时调用，把 schema 传给 chat() 的 tools 参数。
        LLM 根据这些 schema 决定要不要调工具、调哪个、传什么参数。

        Returns:
            [{"type": "function", "function": {...}}, ...]
        """
        return [tool.to_openai_schema() for tool in self._tools.values()]
