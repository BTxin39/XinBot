import typer

from app.cli.chat import chat_app
from app.cli.config import config_app
from app.cli.status import status_app
from app.cli.version import version_app
from app.cli.memory import memory_app
from app.cli.prompt import prompt_app
from rich.console import Console
from app.cli.start import start_app
from app.cli.doctor import doctor_app
from app.cli.persona import persona_app

app = typer.Typer()
console = Console()

app.add_typer(chat_app, name="chat", help="Start chat session with the AI companion")
app.add_typer(config_app, name="config", help="Manage configuration settings")
app.add_typer(status_app, name="status", help="Show current agent status")
app.add_typer(prompt_app, name="prompt", help="Manage prompt templates")
app.add_typer(memory_app, name="memory", help="Manage chat memory")
app.add_typer(version_app, name="version", help="Show version information")
app.add_typer(start_app, name="start", help="Start desktop pet CLI")
app.add_typer(doctor_app, name="doctor", help="Check XinBot configuration")
app.add_typer(persona_app, name="persona", help="Manage AI persona")


if __name__ == "__main__":
    app()
