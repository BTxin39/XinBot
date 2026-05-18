import typer
from rich.console import Console

from app.agent.agent import Agent

status_app = typer.Typer()
console = Console()


@status_app.callback(invoke_without_command=True)
def status():
    agent = Agent()
    status_info = agent.get_status()
    console.print(f"""
[bold green]Agent Status[/bold green]

Emotion: {status_info.emotion}
Provider: {status_info.provider}
Model: {status_info.model_name}
Memory Messages: {status_info.memory_messages}
""")
