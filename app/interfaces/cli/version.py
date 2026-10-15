from app.core.state import AgentState
import typer 
from rich.console import Console

version_app = typer.Typer()
console = Console()

@version_app.callback(invoke_without_command=True)
def version():
    agent = AgentState()
    console.print(r"""
[bold green]                                             
          ,--.        ,--.            ,--.   
,--.  ,--.`--',--,--, |  |-.  ,---. ,-'  '-. 
 \  `'  / ,--.|      \| .-. '| .-. |'-.  .-' 
 /  /.  \ |  ||  ||  || `-' |' '-' '  |  |   
'--'  '--'`--'`--''--' `---'  `---'   `--'   
[/bold green]

[pink]version: [/pink]0.0.1
[pink]github: [/pink]https://github.com/BTxin39

[blue]Try [yellow]"xinbot --help"[/yellow] for help![/blue]
""")
