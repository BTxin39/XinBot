from rich.console import Console
from app.agent.agent import Agent
from app.config.runtime import RuntimeConfig

console = Console()

class CommandHandler:
    def __init__(self, agent: Agent):
        self.agent = agent

    def handle(self, user_input: str) -> bool:
        if not user_input.startswith("/"):
            return False
        command = user_input[1:]

        if command == "help":
            self._help()
        elif command == "clear":
            self._clear_memory()
        elif command in [
            "happy",
            "sad",
            "angry",
            "sleepy",
            "normal"
        ]:
            self._change_emotion(command)
        elif command == "config":
            self._show_config()
        elif command == "status":
            self._show_status()
        else:
            console.print(f"[red]UNKNOWN COMMAND[/red]")
        return True
        

    def _help(self):
        console.print("""
[bold green]Commands:[/bold green]

/help
/clear
/happy
/sad
/angry
/sleepy
/normal
""")

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
