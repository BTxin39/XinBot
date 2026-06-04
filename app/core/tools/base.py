"""工具系统的基类和协议定义。

这个模块定义了 XinBot 工具系统的最底层抽象：
- ToolParameter: 描述一个工具参数的元数据（给 LLM 看）
- DangerLevel: 工具的危险等级（安全审批用）
- BaseTool: 所有工具必须继承的抽象基类

工具调用链路（概述）：
  LLM 返回 tool_calls → ToolManager 解析 JSON → 找到对应的 BaseTool 子类
  → guard.check() 安全检查 → tool.execute(**kwargs) → 结果返回给 LLM
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum


@dataclass
class ToolParameter:
    """工具参数的元数据。

    每个参数会被转换为 OpenAI Function Calling schema 中的一个 property。
    例如：
        ToolParameter(name="path", type="string", description="文件路径", required=True)
    生成 schema：
        {"type": "string", "description": "文件路径"}

    Attributes:
        name: 参数名。LLM 填 arguments 时用这个 key。
        type: JSON Schema 类型。常用 "string" / "number" / "boolean"。
        description: 给 LLM 看的参数说明。写得越清楚，LLM 调用越准确。
        required: 是否必填。必填参数会出现在 schema 的 required 列表里。
        enum: 可选值列表。LLM 只能从这些值中选。适合情绪、状态等固定选项。
    """
    name: str
    type: str
    description: str
    required: bool = True
    enum: list[str] | None = None


class DangerLevel(Enum):
    """工具的危险等级，用于安全审批。

    设计意图：
    - SAFE: 无副作用的操作，不需要用户审批。get_time, set_emotion 等。
    - READ_ONLY: 读取系统状态，理论无副作用但涉及隐私。read_file 等。
      当前默认放行，但留了扩展点——以后可以加"需用户确认一次"的逻辑。
    - DANGEROUS: 会修改系统状态的操作。write_file, delete_file 等。
      执行前必须通过审批回调征得用户同意。

    为什么用 Enum 而不是字符串？
    - IDE 自动补全，不会拼错 "dangrous"
    - 类型检查：guard.check() 的参数类型是 DangerLevel，不是 str
    - 以后加新等级（如 NETWORK）时，所有 match-case 都会报 exhaustiveness check
    """
    SAFE = "safe"
    READ_ONLY = "read_only"
    DANGEROUS = "dangerous"


class BaseTool(ABC):
    """工具的抽象基类。所有工具必须继承此类。

    子类需要做的事：
    1. 定义 name（工具名，LLM 通过这个名字调用）
    2. 定义 description（工具说明，LLM 据此判断何时调用）
    3. 定义 parameters（参数列表，告诉 LLM 传什么参数）
    4. 定义 danger_level（默认 SAFE，危险工具需要覆盖）
    5. 实现 execute(**kwargs) -> str（执行逻辑）

    生命周期：
    1. 实例化 → 注册到 ToolRegistry
    2. LLM 返回 tool_calls → ToolManager 找到对应实例
    3. ToolGuard 检查 danger_level → 通过则调用 execute()
    4. execute() 返回字符串 → 作为 tool role 消息发回 LLM

    execute() 的设计约定：
    - 必须返回字符串（str），而不是 None 或异常
    - 如果执行失败，返回错误描述字符串，不要抛异常
      这样 LLM 能收到错误信息并调整行为，而不是 Agent Loop 崩溃
    - **kwargs 接收 LLM 传入的参数。参数名与 ToolParameter.name 对应
    """

    # 子类必须覆盖这些属性
    name: str
    description: str
    parameters: list[ToolParameter] = []
    danger_level: DangerLevel = DangerLevel.SAFE

    def to_openai_schema(self) -> dict:
        """生成 OpenAI Function Calling 兼容的工具定义。

        转换过程：
        1. 遍历 self.parameters，每个 ToolParameter → 一个 JSON Schema property
        2. 收集 required=True 的参数到 required 列表
        3. 组装成 {"type": "function", "function": {...}} 格式

        Returns:
            OpenAI tools 参数的 dict。注册到 ToolRegistry 后会批量传给 LLM。
        """
        properties: dict = {}
        required: list[str] = []
        for param in self.parameters:
            prop: dict = {"type": param.type, "description": param.description}
            if param.enum:
                prop["enum"] = param.enum
            properties[param.name] = prop
            if param.required:
                required.append(param.name)

        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                },
            },
        }

    def get_danger_level(self) -> str:
        return self.danger_level.value

    @abstractmethod
    def execute(self, **kwargs) -> str:
        """执行工具逻辑。

        Args:
            **kwargs: LLM 传入的参数，key 与 ToolParameter.name 对应。

        Returns:
            str: 执行结果。成功返回结果，失败返回错误描述。
                 不要返回 None，不要抛异常。

        实现提示：
        - 使用 kwargs.get("param_name") 或强制参数名（如 def execute(self, path: str)）
        - 验证参数合法性，不合法的参数返回错误字符串
        - 对于 DANGEROUS 工具，参数验证和执行逻辑分开：
          先检查参数（路径是否合法），再执行（此时 guard 已审批通过）
        """
        ...
