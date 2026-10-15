"""xinbot 命令行入口。

P6 移除了两处历史遗留：
    - `chat` 子命令：早已废弃并由 `start cli` / `debug` 取代，其模块只剩空壳；
    - `start fastapi` / `start live_2d`：`deprecated=True` 的占位子命令。
"""

import typer
from rich.console import Console

from app.interfaces.cli.config import config_app
from app.interfaces.cli.debug import debug_app
from app.interfaces.cli.doctor import doctor_app
from app.interfaces.cli.memory import memory_app
from app.interfaces.cli.persona import persona_app
from app.interfaces.cli.prompt import prompt_app
from app.interfaces.cli.rag import rag_app
from app.interfaces.cli.start import start_app
from app.interfaces.cli.status import status_app
from app.interfaces.cli.version import version_app

app = typer.Typer()
console = Console()

app.add_typer(config_app, name="config", help="Manage configuration settings")
app.add_typer(status_app, name="status", help="Show current agent status")
app.add_typer(prompt_app, name="prompt", help="Manage prompt templates")
app.add_typer(memory_app, name="memory", help="Manage chat memory")
app.add_typer(version_app, name="version", help="Show version information")
app.add_typer(start_app, name="start", help="启动桌宠：cli 终端 / web 网页（默认端口 3796）")
app.add_typer(doctor_app, name="doctor", help="Check XinBot configuration")
app.add_typer(persona_app, name="persona", help="Manage AI persona")
app.add_typer(rag_app, name="rag", help="Manage knowledge base (RAG)")
app.add_typer(debug_app, name="debug", help="Start debug chat session (no Rich UI)")


if __name__ == "__main__":
    app()
