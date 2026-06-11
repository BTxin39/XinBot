from dataclasses import dataclass
from typing import Callable


from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from app.core.agent import Agent

console = Console()


@dataclass
class Command:
    name: str
    help_description: str
    handler: Callable[..., None]
    accepts_arg: bool = False


class CommandHandler:
    def __init__(self, agent: Agent):
        self.agent = agent
        self.handlers: dict[str, Command] = {}
        self.add_handlers()

    def add_handlers(self):
        """注册所有可用的命令处理器"""
        self.handlers['help'] = Command(
            name='help',
            help_description='Show available commands',
            handler=self._help
        )
        self.handlers['clear'] = Command(
            name='clear',
            help_description='Clear agent memory',
            handler=self._clear_memory
        )
        self.handlers['happy'] = Command(
            name='happy',
            help_description='Change emotion to happy',
            handler=lambda: self._change_emotion('happy')
        )
        self.handlers['sad'] = Command(
            name='sad',
            help_description='Change emotion to sad',
            handler=lambda: self._change_emotion('sad')
        )
        self.handlers['angry'] = Command(
            name='angry',
            help_description='Change emotion to angry',
            handler=lambda: self._change_emotion('angry')
        )
        self.handlers['sleepy'] = Command(
            name='sleepy',
            help_description='Change emotion to sleepy',
            handler=lambda: self._change_emotion('sleepy')
        )
        self.handlers['normal'] = Command(
            name='normal',
            help_description='Change emotion to normal',
            handler=lambda: self._change_emotion('normal')
        )
        self.handlers['config'] = Command(
            name='config',
            help_description='Show runtime configuration',
            handler=self._show_config
        )
        self.handlers['status'] = Command(
            name='status',
            help_description='Show agent status',
            handler=self._show_status
        )
        self.handlers['remember'] = Command(
            name='remember',
            help_description='Extract long-term memory from current conversation',
            handler=self._remember_now,
        )
        self.handlers['history'] = Command(
            name='history',
            help_description='Show N recent messages (e.g. /history 10)',
            handler=self._show_history,
            accepts_arg=True,
        )

    def handle(self, user_input: str) -> bool:
        if not user_input.startswith("/"):
            return False

        parts = user_input[1:].split(maxsplit=1)
        command_name = parts[0]
        arg = parts[1] if len(parts) > 1 else ""

        if command_name in self.handlers:
            cmd = self.handlers[command_name]
            if cmd.accepts_arg:
                cmd.handler(arg)
            else:
                cmd.handler()
        else:
            console.print(f"[red]UNKNOWN COMMAND[/red]")
            self._help()

        return True    

    def _help(self):
        console.print("[bold green]Commands:[/bold green]")
        for cmd in self.handlers.values():
            console.print(f"/{cmd.name} - {cmd.help_description}")

    def _clear_memory(self):
        self.agent.memory.clear()
        console.print(
            "[yellow]Memory cleared[/yellow]"
        )

    def _change_emotion(self, emotion: str):
        self.agent.change_emotion(emotion)

        console.print(
            f"[cyan]Emotion -> {emotion}[/cyan]"
        )

    def _show_config(self):
        config = self.agent.config

        console.print(f"""
    [bold green]Runtime Config[/bold green]

    Model: {config.model_name}
    Provider: {config.provider}
    Temperature: {config.temperature}
    Memory Limit: {config.max_memory_messages}
    """)

    def _remember_now(self):
        result = self.agent.remember_now()
        console.print(f"[green]{result}[/green]")

    def _show_status(self):
        status = self.agent.get_status()

        console.print(f"""
    [bold green]Agent Status[/bold green]

    Emotion: {status.emotion}
    Provider: {status.provider}
    Model: {status.model_name}
    Memory Messages: {status.memory_messages}
    """)

    def _show_history(self, arg: str = ""):
        """显示最近 N 条对话历史。

        /history     → 默认 10 条
        /history 5   → 最近 5 条
        """
        try:
            count = int(arg) if arg else 10
        except ValueError:
            console.print(f"[red]无效参数: {arg}，请输入数字[/red]")
            return

        messages = self.agent.memory.get_message()
        if not messages:
            console.print("[dim]暂无对话历史。[/dim]")
            return

        recent = messages[-count:]
        table = Table(title=f"最近 {len(recent)} 条对话", border_style="blue")
        table.add_column("#", style="dim", width=4)
        table.add_column("Role", style="bold cyan", width=10)
        table.add_column("Content", style="white")

        total = len(messages)
        for i, msg in enumerate(recent):
            idx = total - len(recent) + i + 1
            role = msg.get("role", "?")
            content = msg.get("content", "")
            # 截断长内容用于展示
            display = content[:200] + "…" if len(content) > 200 else content
            if not display:
                # 可能是 tool_calls 消息
                if msg.get("tool_calls"):
                    display = "[tool_calls]"
                elif msg.get("tool_call_id"):
                    display = f"[tool_result] {msg.get('tool_call_id', '')}"

            role_style = {
                "user": "[bold yellow]user[/bold yellow]",
                "assistant": "[bold green]assistant[/bold green]",
                "system": "[dim]system[/dim]",
                "tool": "[magenta]tool[/magenta]",
            }.get(role, role)

            table.add_row(str(idx), role_style, display)

        console.print(table)
