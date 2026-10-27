"""情绪变化事件的默认监听器。

归属说明（见 docs/DECISIONS/DECISIONS_V0.2.0.md §8 R4）：
本模块由 `app/core/agent.py` 在构造时订阅，因此它**属于核心的运行时依赖**，
不得 import 渲染库——原先 `from rich.console import Console` 会让
任何走 `Agent` 的调用链（包括 Web）都被迫加载 rich，也让命令层无法脱离 rich 复用。

现在用纯 `print()` 输出，行为（每次情绪变化打印一行）保持不变。
`core/agent.py` 中 MCP 注册失败也是用 `print(..., file=sys.stderr)` 报告的，
与此处口径一致。

后续可选项（未做，需要产品决策）：`SetEmotionTool` 由 LLM 调用时同样会打印，
可能显得啰嗦；若要收敛，应把"是否打印"改为构造注入，而不是恢复跨层依赖。
"""

from app.events.events import EmotionChangedEvent


def on_emotion_changed(event: EmotionChangedEvent) -> None:
    print(
        "\nEmotion changed:\n"
        f"{event.old_emotion}\n"
        "→\n"
        f"{event.new_emotion}\n"
    )
