"""内置系统工具。

这些是 XinBot 开箱即用的工具，注册在 Agent._register_builtin_tools() 中。

新增工具时参考这里的模式：
1. 继承 BaseTool
2. 定义 name, description, parameters
3. 🆕 定义 danger_level（默认 SAFE，危险操作要覆盖）
4. 实现 execute()，返回 str

execute() 的编写规范：
- 返回 str，不返回 None，不抛异常
- 参数验证失败返回错误描述字符串（如 "无效情绪: xxx"）
- 对外部依赖（文件、网络）的失败要捕获并返回友好错误
- 如果工具需要访问 Agent 实例（如改情绪），通过构造器注入
"""

from datetime import datetime

from app.core.tools.base import BaseTool, DangerLevel, ToolParameter


class GetTimeTool(BaseTool):
    """获取当前日期和时间。

    最简单的工具示例：无参数、无副作用、串行输出。
    适合作为新工具开发的参考模板。
    """
    name = "get_time"
    description = "获取当前的日期和时间"
    parameters = []             # 无参数工具
    danger_level = DangerLevel.SAFE  # 纯查询，无副作用

    def execute(self, **kwargs) -> str:
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class SetEmotionTool(BaseTool):
    """改变 AI 桌宠的情绪状态。

    工具设计要点：
    - 通过构造器注入 Agent 引用，而不是 import 全局变量
      这样测试时可以用 FakeAgent 替代真 Agent
    - 参数有 enum 约束，LLM 只能从给定值中选择
    - 在 execute 中再次验证参数，即使 LLM 传了不合法的值也不会崩溃
      （虽然 OpenAI/DeepSeek 一般会遵守 enum，但防御性验证不花代价）
    """
    name = "set_emotion"
    description = "改变 AI 桌宠的情绪状态。调用此工具来响应用户的情绪相关请求。"

    parameters = [
        ToolParameter(
            name="emotion",
            type="string",
            description="要设置的情绪",
            enum=["normal", "happy", "sad", "angry", "sleepy"],
        )
    ]
    danger_level = DangerLevel.SAFE  # 只改内存状态，不写文件不发网络

    def __init__(self, agent):
        """注入 Agent 引用。

        Args:
            agent: Agent 实例。工具通过 agent.change_emotion() 修改情绪。
                   测试时传入 FakeAgent。
        """
        self.agent = agent

    def execute(self, emotion: str) -> str:
        # 防御性验证：即使 LLM 99% 遵守 enum，也要处理那 1%
        valid = {"normal", "happy", "sad", "angry", "sleepy"}
        if emotion not in valid:
            return f"无效情绪: {emotion}。可选: {', '.join(sorted(valid))}"
        self.agent.change_emotion(emotion)
        return f"情绪已切换为 {emotion}"


class GetStatusTool(BaseTool):
    """获取 Agent 的运行时状态。

    这是一个只读工具，展示了如何通过构造器注入来访问 Agent 内部状态。
    """
    name = "get_status"
    description = "获取 AI 桌宠的当前状态，包括情绪、使用的模型、记忆数量"

    parameters = []
    danger_level = DangerLevel.SAFE  # 只读查询

    def __init__(self, agent):
        """注入 Agent 引用。

        Args:
            agent: Agent 实例。工具通过 agent.get_status() 读取状态。
        """
        self.agent = agent

    def execute(self, **kwargs) -> str:
        status = self.agent.get_status()
        return (
            f"当前情绪: {status.emotion}\n"
            f"模型: {status.model_name}\n"
            f"记忆消息数: {status.memory_messages}"
        )
