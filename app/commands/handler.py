from dataclasses import dataclass
from typing import Callable

from rich.console import Console
from app.core.agent import Agent

console = Console()

@dataclass
class Command:
    name: str
    help_description: str
    handler: Callable[[], None]


class CommandHandler:
    def __init__(self, agent: Agent):
        self.agent = agent
        self.handlers: dict[str, Command] = {}
        self.add_handlers()

    def add_handlers(self):
        """注册所有可用的命令处理器"""
        # 注册内置命令
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

    def handle(self, user_input: str) -> bool:
        if not user_input.startswith("/"):
            return False

        command = user_input[1:]

        if command in self.handlers:
            self.handlers[command].handler()
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

    def _show_status(self):
        status = self.agent.get_status()

        console.print(f"""
    [bold green]Agent Status[/bold green]

    Emotion: {status.emotion}
    Provider: {status.provider}
    Model: {status.model_name}
    Memory Messages: {status.memory_messages}
    """)
