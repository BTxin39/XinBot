import typer
from rich.console import Console
from rich.table import Table

from app.core.persona import PERSONAS
from app.config.runtime import RuntimeConfig

persona_app = typer.Typer()
console = Console()


@persona_app.command("list")
def list_personas():
    config = RuntimeConfig.load()
    table = Table(title="Available Personas")
    table.add_column("Name", style="cyan")
    table.add_column("Display Name")
    table.add_column("Traits")
    table.add_column("Current")

    for name, p in PERSONAS.items():
        is_current = "★" if name == config.persona_name else ""
        table.add_row(name, p.display_name, "、".join(p.traits), is_current)

    console.print(table)


@persona_app.command("show")
def show_persona(
    name: str = typer.Argument(default="", help="Persona name to show"),
):
    config = RuntimeConfig.load()
    target = name or config.persona_name
    persona = PERSONAS.get(target)
    if persona is None:
        console.print(f"[red]Unknown persona: {target}[/red]")
        available = ", ".join(PERSONAS.keys())
        console.print(f"[dim]Available: {available}[/dim]")
        raise typer.Exit(code=1)

    console.print(f"[bold cyan]{persona.display_name}[/bold cyan]")
    console.print(f"  Traits: {'、'.join(persona.traits)}")
    console.print(f"  Style: {persona.speaking_style}")
    console.print(f"  Background: {persona.background}")
    console.print(f"  Constraints:")
    for c in persona.constraints:
        console.print(f"    - {c}")


@persona_app.command("set")
def set_persona(
    name: str = typer.Argument(..., help="Persona name to switch to"),
):
    if name not in PERSONAS:
        console.print(f"[red]Unknown persona: {name}[/red]")
        available = ", ".join(PERSONAS.keys())
        console.print(f"[dim]Available: {available}[/dim]")
        raise typer.Exit(code=1)

    config = RuntimeConfig.load()
    config.persona_name = name
    config.save()
    console.print(
        f"[green]Persona set to: {PERSONAS[name].display_name}[/green]"
    )
    console.print(
        "[dim]Restart chat session for the new persona to take effect.[/dim]"
    )
