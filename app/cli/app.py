import typer

from app.cli.chat import chat_app
from app.cli.config import config_app
from app.cli.status import status_app
from app.cli.version import version_app
from app.cli.memory import memory_app

app = typer.Typer()

app.add_typer(chat_app, name="chat")
app.add_typer(config_app, name="config")
app.add_typer(status_app, name="status")
app.add_typer(version_app, name="version")
app.add_typer(memory_app, name="memory")

if __name__ == "__main__":
    app()
