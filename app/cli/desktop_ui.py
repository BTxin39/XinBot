"""现代极简桌面宠物 UI —— 双列聊天气泡布局。

左侧：Q 版 ASCII 宠物
右侧：聊天气泡（用户黄色竖线，AI 青色竖线）
底部：快捷命令 + 输入行
"""

from rich.align import Align
from rich.columns import Columns
from rich.console import Console, Group
from rich.padding import Padding
from rich.rule import Rule
from rich.text import Text

from app.core.agent import Agent
from app.config.cli_ui_settings import UISettings
from app.cli.ascii_pets import Q_PETS, EMOTION_EMOJI


class DesktopPetUI:
    """现代极简双列聊天 UI。"""

    COMMANDS_HINT = "/help /clear /happy /sad /angry /sleepy /normal /status /history /remember /config"

    def __init__(
        self,
        console: Console,
        settings: UISettings | None = None,
    ):
        self.console = console
        self.settings = settings or UISettings.load()
        self._last_user_input = ""
        self._last_reply = ""

    # ── SessionUI protocol ──────────────────────────────────────

    def on_start(self, agent: Agent) -> None:
        self._last_user_input = ""
        self._last_reply = ""
        self.console.clear()
        self.console.print(self._build_welcome(agent))

    def on_before_reply(self, agent: Agent, user_input: str) -> None:
        self._last_user_input = user_input
        self._last_reply = ""
        self.console.clear()
        self.console.print(self._build_chat_view(agent, user_input, "思考中..."))
        # 移动光标到输入区下方
        pet_lines = self._pet_height(agent)
        print("\n" * (pet_lines + 4))

    def on_chunk(self, agent: Agent, chunk: str) -> None:
        pass

    def on_after_reply(self, agent: Agent, full_response: str) -> None:
        self.console.clear()
        self.console.print(
            self._build_chat_view(agent, self._last_user_input, full_response)
        )
        # 输出换行使输入提示出现在正确位置
        pet_lines = self._pet_height(agent)
        print("\n" * (pet_lines + 3))

    # ── 视图构建 ─────────────────────────────────────────────────

    def _pet_height(self, agent: Agent) -> int:
        """返回当前宠物图案的行数。"""
        pet = self._pet_picture(agent)
        return pet.count("\n")

    def _pet_picture(self, agent: Agent) -> str:
        """获取当前情绪的宠物图案。"""
        emotion = agent.state.emotion
        pic = self.settings.emotion_pictures.get(emotion)
        if pic and pic not in ("[picture_normal]", "[picture_happy]", "[picture_sad]", "[picture_angry]", "[picture_sleepy]"):
            return pic
        return Q_PETS.get(emotion, Q_PETS["normal"]).strip()

    def _build_welcome(self, agent: Agent) -> Group:
        """首次启动渲染欢迎画面。"""
        return self._build_chat_view(agent, "", "嗨~ 我在这里陪你哦！输入内容开始聊天 ✨")

    def _build_chat_view(
        self,
        agent: Agent,
        user_input: str,
        reply: str,
    ) -> Group:
        """构建完整视图。"""
        pet_text = self._pet_picture(agent)
        pet_lines = pet_text.split("\n")
        max_pet_width = max(len(line) for line in pet_lines) if pet_lines else 10

        # 左侧宠物列 —— 固定宽度，顶部对齐
        pet_render = Text(pet_text, style="bold")
        # 给右侧的聊天内容加上 padding 左对齐
        pet_col = Align.left(pet_render, style="")

        # 右侧聊天列
        chat = self._build_chat_column(agent, user_input, reply)

        # 双列布局
        columns = Columns(
            [pet_col, chat],
            width=max_pet_width + 4,
            equal=False,
            expand=True,
        )

        # 顶栏
        emoji = EMOTION_EMOJI.get(agent.state.emotion, "💚")
        persona = agent.persona.display_name
        header = Text(
            f"  {emoji}  {persona}  ·  {agent.state.emotion}  ·  {agent.config.provider}/{agent.config.model_name}",
            style="dim",
        )
        top_rule = Rule(header, style="bright_black")

        # 底部快捷命令 + 输入提示
        hint = Text(f"\n  {self.COMMANDS_HINT}", style="dim italic")
        

        return Group(
            top_rule,
            Padding("", (0, 0)),
            columns,
            hint,
        )

    def _build_chat_column(
        self,
        agent: Agent,
        user_input: str,
        reply: str,
    ) -> Text:
        """构建右侧聊天气泡列。"""
        chat = Text()

        if user_input:
            chat.append("│  ", style="yellow")
            chat.append("You  ", style="bold yellow")
            chat.append(user_input, style="")
            chat.append("\n\n")

        if reply:
            chat.append("│  ", style="cyan")
            chat.append(f"{agent.persona.display_name}  ", style="bold cyan")
            chat.append(reply, style="")

        return chat
