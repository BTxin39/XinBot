"""xinbot model —— 管理桌宠外观模型（Live2D / 精灵图）。

`import` 与 Web 的"上传 ZIP"走完全相同的校验链路
（`app/services/live2d_service.py`），因此命令行与网页行为一致。
"""

from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from app.services import live2d_service
from app.services.live2d_service import ModelImportError

model_app = typer.Typer()
console = Console()

FORMAT_LABELS = {
    "cubism3": "Live2D Cubism 3/4/5",
    "cubism2": "Live2D Cubism 2.1（旧版）",
    "sprite": "精灵图（8×9）",
}


@model_app.command("import")
def import_model(
    path: str = typer.Argument(..., help="模型 ZIP 路径"),
    quiet: bool = typer.Option(False, "--quiet", "-q", help="只输出结果，不打印明细"),
):
    """从 ZIP 导入一个桌宠外观模型。

    支持 Live2D Cubism 3/4/5（*.model3.json）、Cubism 2.1（*.model.json）
    与 Codex 8×9 精灵图（pet.json），也支持夹带网页资源的工程包。

    示例：

        xinbot model import scratch/miku.zip
        xinbot model import D:/downloads/character.zip
    """
    source = Path(path)
    if not source.is_file():
        console.print(f"[red]找不到文件：[/red]{path}")
        raise typer.Exit(code=1)

    try:
        result = live2d_service.import_from_path(source)
    except ModelImportError as error:
        console.print(f"[red]导入失败：[/red]{error}")
        if error.detail:
            console.print(f"[yellow]{error.detail}[/yellow]")
        raise typer.Exit(code=1) from error

    console.print(f"[green]✓ 已导入[/green] {result['name']}  [dim]({result['kind']})[/dim]")
    if quiet:
        return

    console.print(f"[dim]目录：{result['location']}[/dim]")
    console.print(f"[dim]清单：{result['url']}[/dim]")
    for warning in result.get("warnings") or []:
        console.print(f"[yellow]⚠ {warning}[/yellow]")

    others = [item for item in result.get("candidates") or [] if item["kind"] != result["kind"]]
    if others:
        console.print(
            f"[dim]压缩包里还有 {len(others)} 个其它格式的模型，本次按优先级只导入了 "
            f"{FORMAT_LABELS.get(result['kind'], result['kind'])}。[/dim]"
        )


@model_app.command("list")
def list_models():
    """列出已导入的外观模型。"""
    rows = live2d_service.catalog()
    state = live2d_service.runtime_state()

    if not rows:
        console.print("[dim]还没有导入任何模型。用 `xinbot model import <zip>` 导入。[/dim]")
        return

    table = Table(title="已导入的外观模型")
    table.add_column("名称", style="cyan")
    table.add_column("格式")
    table.add_column("运行时", justify="center")
    for row in rows:
        info = state.get(row["kind"], {})
        if info.get("ready"):
            runtime = "[green]就绪[/green]"
        else:
            runtime = f"[red]缺 {info.get('file')}[/red]"
        table.add_row(row["name"], FORMAT_LABELS.get(row["kind"], row["kind"]), runtime)
    console.print(table)


@model_app.command("remove")
def remove_model(
    name: str = typer.Argument(..., help="要删除的模型名（见 `xinbot model list`）"),
    force: bool = typer.Option(False, "--force", "-f", help="跳过确认"),
):
    """删除一个已导入的外观模型（只删 pet/imported/ 下的内容）。"""
    try:
        row = live2d_service.find_by_name(name)
    except ModelImportError as error:
        console.print(f"[red]{error}[/red]")
        if error.detail:
            console.print(f"[dim]{error.detail}[/dim]")
        raise typer.Exit(code=1) from error

    if not force:
        if not typer.confirm(f"确认删除模型 '{row['name']}'（{FORMAT_LABELS.get(row['kind'], row['kind'])}）？"):
            console.print("[dim]已取消。[/dim]")
            return

    try:
        result = live2d_service.remove_model(row["name"])
    except ModelImportError as error:
        console.print(f"[red]删除失败：{error}[/red]")
        raise typer.Exit(code=1) from error

    console.print(f"[green]✓ 已删除[/green] {result['name']}")
    console.print(f"[dim]目录：{result['removed']}[/dim]")
    if result["remaining"]:
        console.print(f"[dim]剩余：{'、'.join(result['remaining'])}[/dim]")
    else:
        console.print("[dim]导入目录已空。[/dim]")


@model_app.command("rename")
def rename_model(
    name: str = typer.Argument(..., help="当前模型名"),
    new_name: str = typer.Argument(..., help="新名字"),
):
    """重命名已导入的模型（会同步清单文件名）。"""
    try:
        result = live2d_service.rename_model(name, new_name)
    except ModelImportError as error:
        console.print(f"[red]重命名失败：{error}[/red]")
        raise typer.Exit(code=1) from error
    console.print(
        f"[green]✓ 已重命名[/green] {result['old_name']} → {result['name']}"
    )
    console.print(f"[dim]清单：{result['manifest']}[/dim]")


@model_app.command("runtimes")
def runtimes():
    """查看各 Live2D 版本的运行时就绪情况。"""
    table = Table(title="外观运行时")
    table.add_column("格式", style="cyan")
    table.add_column("状态", justify="center")
    table.add_column("需要文件", style="dim")
    table.add_column("说明")

    labels = {key: value for key, value in FORMAT_LABELS.items()}
    state = live2d_service.runtime_state()
    for kind in ("cubism3", "cubism2", "sprite"):
        info = state.get(kind, {})
        ready = "[green]就绪[/green]" if info.get("ready") else "[red]缺失[/red]"
        table.add_row(
            labels.get(kind, kind),
            ready,
            info.get("file") or "—",
            info.get("missing_hint") or "无需额外运行时",
        )
    console.print(table)
