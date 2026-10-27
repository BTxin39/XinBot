"""`xinbot reminder` —— 提醒与日程。

提醒通过桌宠气泡 + 语音提示，不弹窗抢焦点。
"""

import typer
from rich.console import Console
from rich.table import Table

reminder_app = typer.Typer(help="提醒与日程（久坐、喝水、定时事项）。")
console = Console()


def _book():
    from app.services import reminder_service

    return reminder_service.book()


@reminder_app.callback(invoke_without_command=True)
def reminder(ctx: typer.Context):
    if ctx.invoked_subcommand is not None:
        return
    listing()


@reminder_app.command("add")
def add(
    text: str = typer.Argument(..., help="提醒内容"),
    at: str = typer.Option(..., "--at", help="每天用 HH:MM；一次性用 YYYY-MM-DDTHH:MM"),
    repeat: str = typer.Option("once", "--repeat", help="once（一次性）或 daily（每天）"),
):
    """新增提醒。

    示例:
        xinbot reminder add 喝水 --at 10:00 --repeat daily
        xinbot reminder add 开会 --at 2026-05-01T09:00
    """
    try:
        item = _book().add(text, at, repeat)
    except ValueError as error:
        console.print(f"[red]{error}[/red]")
        raise typer.Exit(1) from error
    console.print(f"[green]已添加[/green] {item.id}｜{item.text}｜{item.at}｜{item.repeat}")


@reminder_app.command("list")
def listing():
    """列出全部提醒。"""
    book = _book()
    items = book.all()
    if not items:
        console.print("[dim]还没有提醒。用 `xinbot reminder add` 添加。[/dim]")
        return
    table = Table(title="提醒")
    table.add_column("ID", style="cyan", no_wrap=True)
    table.add_column("内容")
    table.add_column("时间", no_wrap=True)
    table.add_column("重复", no_wrap=True)
    table.add_column("状态", no_wrap=True)
    for item in items:
        if not item.enabled:
            status = "[dim]已关闭[/dim]"
        elif item.repeat == "once" and item.fired:
            status = "[dim]已提醒[/dim]"
        elif item.repeat == "daily" and item.last_fired_date:
            status = f"[green]今天已提醒[/green]"
        else:
            status = "[green]等待中[/green]"
        table.add_row(item.id, item.text, item.at, item.repeat, status)
    console.print(table)
    state = book.state()
    console.print(f"[dim]共 {state['count']} 条｜当前到期 {state['due']} 条｜{state['now']}[/dim]")


@reminder_app.command("remove")
def remove(reminder_id: str = typer.Argument(..., help="提醒 ID（见 list）")):
    """删除一条提醒。"""
    if _book().remove(reminder_id):
        console.print("[green]已删除[/green]")
    else:
        console.print("[red]找不到该提醒[/red]")
        raise typer.Exit(1)


@reminder_app.command("toggle")
def toggle(
    reminder_id: str = typer.Argument(...),
    off: bool = typer.Option(False, "--off", help="关闭而不是开启"),
):
    """启用 / 停用一条提醒。"""
    if _book().toggle(reminder_id, not off):
        console.print("[green]已更新[/green]")
    else:
        console.print("[red]找不到该提醒[/red]")
        raise typer.Exit(1)


@reminder_app.command("clear")
def clear(force: bool = typer.Option(False, "--force", "-f", help="跳过确认")):
    """清空所有提醒。"""
    if not force and not typer.confirm("确认清空所有提醒？"):
        console.print("[dim]已取消。[/dim]")
        return
    count = _book().clear()
    console.print(f"[green]已清空 {count} 条[/green]")


@reminder_app.command("status")
def status():
    """查看提醒概况与当前时间。"""
    state = _book().state()
    console.print(
        f"提醒 {state['count']} 条（启用 {state['enabled']}）｜"
        f"当前到期 {state['due']} 条｜现在 {state['now']}"
    )
