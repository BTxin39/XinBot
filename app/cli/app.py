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
from app.cli.rag import rag_app
from app.cli.debug import debug_app

app = typer.Typer()
console = Console()

app.add_typer(chat_app, name="chat", help="(deprecated) use `xinbot start cli` or `xinbot debug` instead")
app.add_typer(config_app, name="config", help="Manage configuration settings")
app.add_typer(status_app, name="status", help="Show current agent status")
app.add_typer(prompt_app, name="prompt", help="Manage prompt templates")
app.add_typer(memory_app, name="memory", help="Manage chat memory")
app.add_typer(version_app, name="version", help="Show version information")
app.add_typer(start_app, name="start", help="Start desktop pet CLI")
app.add_typer(doctor_app, name="doctor", help="Check XinBot configuration")
app.add_typer(persona_app, name="persona", help="Manage AI persona")
app.add_typer(rag_app, name="rag", help="Manage knowledge base (RAG)")
app.add_typer(debug_app, name="debug", help="Start debug chat session (no Rich UI)")


if __name__ == "__main__":
    app()

