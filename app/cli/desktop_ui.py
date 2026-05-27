from rich.align import Align
from rich.console import Console, Group
from rich.panel import Panel
from rich.text import Text

from app.core.agent import Agent
from app.config.ui_settings import UISettings


class DesktopPetUI:
    def __init__(
        self,
        console: Console,
        settings: UISettings | None = None,
    ):
        self.console = console
        self.settings = settings or UISettings.load()

    def render(
        self,
        agent: Agent,
        latest_reply: str | None = None,
        current_input: str | None = None,
    ) -> None:
        self.settings = UISettings.load()
        self.console.clear()
        self.console.print(
            self.build_view(agent, latest_reply, current_input)
        )

    def build_view(
        self,
        agent: Agent,
        latest_reply: str | None,
        current_input: str | None = None,
    ) -> Group:
        pet_picture = self.settings.picture_for(
            agent.state.emotion
        )
        status_line = (
            f"emotion={agent.state.emotion} "
            f"provider={agent.config.provider} "
            f"model={agent.config.model_name} "
            f"memory={agent.config.current_memory_name}"
        )

        picture_panel = Panel(
            Align.center(Text(pet_picture)),
            title="Xin",
            subtitle=status_line,
            border_style="green",
        )

        reply_panel = Panel(
            Text(latest_reply or "等待你的输入。"),
            title="Agent",
            border_style="cyan",
        )

        history_panel = Panel(
            self._history_text(agent),
            title=(
                "History "
                f"(last {self.settings.history_display_lines})"
            ),
            border_style="blue",
        )

        input_panel = Panel(
            Text(current_input or "在下方输入内容，回车发送。"),
            title="User Input",
            border_style="yellow",
        )

        return Group(
            picture_panel,
            history_panel,
            input_panel,
            reply_panel,
        )

    def build_streaming_view(
        self,
        agent: Agent,
        latest_reply: str | None,
        current_input: str | None = None,
    ) -> Group:
        self.settings = UISettings.load()
        return self.build_view(
            agent=agent,
            latest_reply=latest_reply,
            current_input=current_input,
        )

    def _history_text(self, agent: Agent) -> Text:
        messages = agent.memory.get_message()
        limit = self.settings.history_display_lines
        recent_messages = messages[-limit:] if limit > 0 else []

        text = Text()
        if not recent_messages:
            text.append("暂无历史记录。")
            return text

        for message in recent_messages:
            role = message.get("role", "unknown")
            content = message.get("content", "")
            text.append(f"{role}: ", style="bold")
            text.append(f"{content}\n")

        return text
