"""xinbot prompt —— 查看和操作当前角色的完整 prompt。"""

import typer
from rich.console import Console

from app.core.state import AgentState
from app.core.persona import PersonaStore
from app.llm.prompts.prompt_builder import PromptBuilder
from app.config.runtime import RuntimeConfig

prompt_app = typer.Typer()
console = Console()


@prompt_app.command("show")
def show_prompt(
    persona_name: str | None = typer.Argument(None, help="角色名（不填用当前）"),
):
    """预览当前角色的完整 System Prompt。"""
    store = PersonaStore.get()
    config = RuntimeConfig.load()
    target = persona_name or config.persona_name

    persona = store.get_persona(target)
    if persona is None:
        console.print(f"[red]角色 '{target}' 不存在[/red]")
        raise typer.Exit(code=1)

    state = AgentState()
    prompt = PromptBuilder.build(state, persona=persona)

    console.print(f"[bold cyan]System Prompt — {persona.display_name}[/bold cyan]")
    console.print("─" * 60)
    console.print(prompt)
    console.print("─" * 60)
    console.print(f"[dim]角色: {persona.name}  情绪: {state.emotion}[/dim]")


@prompt_app.command("preview")
def preview_emotion(
    persona_name: str | None = typer.Argument(None, help="角色名"),
    emotion: str = typer.Option("normal", "--emotion", "-e", help="情绪名称"),
):
    """预览指定情绪下的完整 prompt。"""
    store = PersonaStore.get()
    config = RuntimeConfig.load()
    target = persona_name or config.persona_name

    persona = store.get_persona(target)
    if persona is None:
        console.print(f"[red]角色 '{target}' 不存在[/red]")
        raise typer.Exit(code=1)

    e = store.get_emotion(emotion)
    if e is None:
        console.print(f"[red]情绪 '{emotion}' 不存在[/red]")
        raise typer.Exit(code=1)

    state = AgentState(emotion=emotion)
    prompt = PromptBuilder.build(state, persona=persona)

    console.print(f"[bold cyan]Prompt — {persona.display_name} @ {emotion}[/bold cyan]")
    console.print("─" * 60)
    console.print(prompt)
