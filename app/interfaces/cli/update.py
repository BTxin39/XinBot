"""`xinbot update` —— 版本检查。

刻意**不做静默自替换**（见 `app/services/update_service.py` 顶部说明）：
只检查、只提示，装不装由用户决定。
"""

from pathlib import Path

import typer
from rich.console import Console

from app.services import update_service

update_app = typer.Typer(help="检查新版本（只提示，不自动替换文件）。")
console = Console()

DEFAULT_MANIFEST = Path("data/update.json")

SAMPLE = """{
  "version": "0.2.1",
  "url": "https://example.com/XinBot-v0.2.1-installer.zip",
  "notes": "修复桌面壳穿透问题",
  "published": "2026-05-01"
}"""


@update_app.callback(invoke_without_command=True)
def update(ctx: typer.Context):
    if ctx.invoked_subcommand is not None:
        return
    status()


@update_app.command("status")
def status():
    """显示当前版本与清单位置。"""
    current = update_service.current_version()
    console.print(f"当前版本：{current}")
    if DEFAULT_MANIFEST.is_file():
        console.print(f"更新清单：{DEFAULT_MANIFEST}（已存在）")
    else:
        console.print(
            f"更新清单：{DEFAULT_MANIFEST}（不存在）\n"
            "[dim]把发布页提供的 update.json 放到该位置，或用 --manifest 指定。[/dim]"
        )


@update_app.command("check")
def check(
    manifest: str = typer.Option(
        "", "--manifest", "-m",
        help=f"清单文件路径（默认 {DEFAULT_MANIFEST}）",
    ),
):
    """检查是否有新版本。"""
    current = update_service.current_version()
    source = Path(manifest) if manifest else DEFAULT_MANIFEST

    if not source.is_file():
        console.print(f"[yellow]找不到清单文件：{source}[/yellow]")
        console.print("[dim]可用 `xinbot update template` 查看清单格式。[/dim]")
        raise typer.Exit(1)

    parsed = update_service.load_manifest(source)
    if parsed is None:
        console.print(f"[red]清单格式不正确：{source}[/red]")
        raise typer.Exit(1)

    info = update_service.check(current, parsed)
    if info is None:
        console.print(f"[green]{update_service.describe(None, current)}[/green]")
        return

    console.print(update_service.describe(info, current))
    console.print(
        "\n[yellow]提示：[/yellow]本项目不会自动替换正在运行的文件。"
        "请下载新版本后按安装说明升级。"
    )


@update_app.command("template")
def template():
    """打印清单文件的格式示例。"""
    console.print(SAMPLE, markup=False, highlight=False)
