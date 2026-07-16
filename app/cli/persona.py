"""xinbot persona —— 管理 AI 角色和情绪。"""

import typer
from rich.console import Console
from rich.table import Table
from rich.markup import escape

from app.core.persona import Persona, PersonaStore
from app.config.runtime import RuntimeConfig

persona_app = typer.Typer()
console = Console()


@persona_app.command("list")
def list_personas():
    """列出所有可用的角色。"""
    store = PersonaStore.get()
    config = RuntimeConfig.load()

    table = Table(title="Personas")
    table.add_column("Name", style="cyan")
    table.add_column("Display Name")
    table.add_column("Traits")
    table.add_column("Type")
    table.add_column("Current")

    for p in store.list_personas():
        is_current = "★" if p.name == config.persona_name else ""
        ptype = "内置" if p.builtin else "自定义"
        table.add_row(p.name, p.display_name, "、".join(p.traits), ptype, is_current)

    console.print(table)


@persona_app.command("show")
def show_persona(
    name: str = typer.Argument(default="", help="角色名称（不填则显示当前）"),
):
    """查看角色详情。"""
    store = PersonaStore.get()
    config = RuntimeConfig.load()
    target = name or config.persona_name

    persona = store.get_persona(target)
    if persona is None:
        console.print(f"[red]角色 '{target}' 不存在[/red]")
        raise typer.Exit(code=1)

    builtin_tag = " [dim](内置)[/dim]" if persona.builtin else " [dim](自定义)[/dim]"
    console.print(f"[bold cyan]{persona.display_name}[/bold cyan]{builtin_tag}")
    console.print(f"  ID: {persona.name}")
    console.print(f"  Traits: {'、'.join(persona.traits)}")
    console.print(f"  Style: {persona.speaking_style}")
    console.print(f"  Background: {persona.background}")
    console.print("  Constraints:")
    for c in persona.constraints:
        console.print(f"    - {c}")


@persona_app.command("set")
def set_persona(
    name: str = typer.Argument(..., help="要切换到的角色名称"),
):
    """切换当前使用的角色。"""
    store = PersonaStore.get()

    if store.get_persona(name) is None:
        console.print(f"[red]角色 '{name}' 不存在[/red]")
        available = ", ".join(p.name for p in store.list_personas())
        console.print(f"[dim]可用: {available}[/dim]")
        raise typer.Exit(code=1)

    config = RuntimeConfig.load()
    config.persona_name = name
    config.save()

    p = store.get_persona(name)
    console.print(f"[green]已切换到: {p.display_name}[/green]")
    console.print("[dim]重启对话后生效。[/dim]")


@persona_app.command("add")
def add_persona(
    name: str = typer.Argument(..., help="角色 ID"),
    display_name: str = typer.Option(..., "--display", "-d", help="显示名称"),
    traits: str = typer.Option("", "--traits", "-t", help="性格特征，逗号分隔"),
    speaking_style: str = typer.Option("", "--style", "-s", help="说话风格"),
    background: str = typer.Option("", "--bg", "-b", help="角色背景"),
    constraints: str = typer.Option("", "--constraints", "-c", help="行为约束，逗号或分号分隔"),
):
    """创建自定义角色。"""
    store = PersonaStore.get()

    if store.get_persona(name) is not None:
        console.print(f"[red]角色 '{name}' 已存在[/red]")
        raise typer.Exit(code=1)

    trait_list = [t.strip() for t in traits.replace("，", ",").split(",") if t.strip()]
    constraint_list = [c.strip() for c in constraints.replace("；", ";").replace("，", ",").replace(";", ",").split(",") if c.strip()]

    persona = Persona(
        name=name,
        display_name=display_name,
        traits=trait_list,
        speaking_style=speaking_style,
        background=background,
        constraints=constraint_list,
        builtin=False,
    )

    try:
        store.add_persona(persona)
        console.print(f"[green]角色 '{display_name}' 创建成功！[/green]")
        console.print(f"[dim]使用 xinbot persona set {name} 切换到该角色[/dim]")
    except ValueError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(code=1)


@persona_app.command("edit")
def edit_persona(
    name: str = typer.Argument(..., help="角色 ID"),
    display_name: str | None = typer.Option(None, "--display", "-d", help="显示名称"),
    traits: str | None = typer.Option(None, "--traits", "-t", help="性格特征，逗号分隔"),
    speaking_style: str | None = typer.Option(None, "--style", "-s", help="说话风格"),
    background: str | None = typer.Option(None, "--bg", "-b", help="角色背景"),
    constraints: str | None = typer.Option(None, "--constraints", "-c", help="行为约束，逗号或分号分隔"),
):
    """修改角色属性。"""
    store = PersonaStore.get()

    if store.get_persona(name) is None:
        console.print(f"[red]角色 '{name}' 不存在[/red]")
        raise typer.Exit(code=1)

    updates = {}
    if display_name is not None:
        updates["display_name"] = display_name
    if traits is not None:
        updates["traits"] = [t.strip() for t in traits.replace("，", ",").split(",") if t.strip()]
    if speaking_style is not None:
        updates["speaking_style"] = speaking_style
    if background is not None:
        updates["background"] = background
    if constraints is not None:
        updates["constraints"] = [c.strip() for c in constraints.replace("；", ";").replace("，", ",").replace(";", ",").split(",") if c.strip()]

    if not updates:
        console.print("[yellow]没有提供任何修改项。[/yellow]")
        return

    try:
        store.update_persona(name, updates)
        console.print(f"[green]角色 '{name}' 已更新。[/green]")
    except ValueError as e:
        console.print(f"[red]{e}[/red]")


@persona_app.command("remove")
def remove_persona(
    name: str = typer.Argument(..., help="要删除的角色 ID"),
    force: bool = typer.Option(False, "--force", "-f", help="跳过确认"),
):
    """删除自定义角色。"""
    store = PersonaStore.get()
    config = RuntimeConfig.load()

    if store.get_persona(name) is None:
        console.print(f"[red]角色 '{name}' 不存在[/red]")
        raise typer.Exit(code=1)

    if config.persona_name == name:
        console.print(f"[red]不能删除正在使用的角色，请先切换到其他角色。[/red]")
        raise typer.Exit(code=1)

    if not force:
        confirm = typer.confirm(f"确认删除角色 '{name}'？")
        if not confirm:
            console.print("[dim]已取消。[/dim]")
            return

    try:
        store.remove_persona(name)
        console.print(f"[green]角色 '{name}' 已删除。[/green]")
    except ValueError as e:
        console.print(f"[red]{e}[/red]")


@persona_app.command("emotions")
def list_emotions():
    """列出所有情绪及其描述。"""
    store = PersonaStore.get()

    table = Table(title="Emotions")
    table.add_column("Name", style="cyan")
    table.add_column("Description")
    table.add_column("Behavior Modifier")

    for e in store.emotions.values():
        table.add_row(e.name, e.description, e.behavior_modifier)

    console.print(table)
