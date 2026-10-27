"""`xinbot plugin` —— 插件管理。

插件是「在当前进程里执行任意 Python 代码」的，所以默认**全部关闭**，
必须显式 `enable`。这个命令组是唯一的开关入口。
"""

from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from app.services import plugin_service

plugin_app = typer.Typer(help="管理工具插件（默认关闭，需显式启用）。")
console = Console()


def _root() -> Path:
    from app.paths import repo_root

    return repo_root()


SAMPLE = '''# data/plugins/hello/plugin.json
{
  "name": "hello",
  "version": "1.0.0",
  "description": "示例插件",
  "entry": "plugin.py",
  "enabled": false
}

# data/plugins/hello/plugin.py
from app.core.tools.base import BaseTool


class Hello(BaseTool):
    name = "hello"
    description = "向用户问好"
    def execute(self, **kwargs):
        return "你好！"


def tools():
    return [Hello()]
'''


@plugin_app.callback(invoke_without_command=True)
def plugin(ctx: typer.Context):
    if ctx.invoked_subcommand is not None:
        return
    listing()


@plugin_app.command("list")
def listing():
    """列出所有插件与加载状态。"""
    root = _root()
    items = plugin_service.discover(root)
    if not items:
        console.print(
            f"[dim]没有插件。目录：{plugin_service.plugins_root(root)}[/dim]\n"
            "[dim]运行 `xinbot plugin init` 生成一个示例插件。[/dim]"
        )
        return

    table = Table(title="插件")
    table.add_column("名称", style="cyan", no_wrap=True)
    table.add_column("版本", no_wrap=True)
    table.add_column("状态", no_wrap=True)
    table.add_column("说明")
    for item in items:
        if item.error:
            status = f"[red]错误：{item.error}[/red]"
        elif item.enabled:
            status = "[green]已启用[/green]"
        else:
            status = "[dim]已停用[/dim]"
        table.add_row(item.name, item.version, status, item.description)
    console.print(table)


@plugin_app.command("enable")
def enable(name: str = typer.Argument(..., help="插件名（见 list）")):
    """启用插件（下次构造 Agent 时生效）。"""
    if plugin_service.set_enabled(_root(), name, True):
        console.print(f"[green]已启用[/green] {name}")
        console.print("[dim]重启后端 / 重新进入对话后生效。[/dim]")
    else:
        console.print(f"[red]找不到插件：{name}[/red]")
        raise typer.Exit(1)


@plugin_app.command("disable")
def disable(name: str = typer.Argument(...)):
    """停用插件。"""
    if plugin_service.set_enabled(_root(), name, False):
        console.print(f"已停用 {name}")
    else:
        console.print(f"[red]找不到插件：{name}[/red]")
        raise typer.Exit(1)


@plugin_app.command("check")
def check():
    """试加载（不注册到 Agent），看哪些插件能正常工作。"""
    root = _root()
    result = plugin_service.load(root)
    if result.loaded:
        console.print(f"[green]可加载：[/green]{'、'.join(result.loaded)}")
        console.print(f"[dim]工具：{', '.join(tool.name for tool in result.tools)}[/dim]")
    else:
        console.print("[yellow]没有可加载的插件[/yellow]")
    for name, reason in result.skipped:
        console.print(f"[dim]跳过 {name}：{reason}[/dim]")


@plugin_app.command("init")
def init(name: str = typer.Argument("hello", help="示例插件名")):
    """在 data/plugins/ 下生成一个示例插件（默认停用）。"""
    directory = plugin_service.plugins_root(_root()) / name
    if directory.exists():
        console.print(f"[red]目录已存在：{directory}[/red]")
        raise typer.Exit(1)
    directory.mkdir(parents=True)
    import json

    (directory / "plugin.json").write_text(json.dumps({
        "name": name, "version": "1.0.0", "description": "示例插件",
        "entry": "plugin.py", "enabled": False,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    (directory / "plugin.py").write_text(
        "from app.core.tools.base import BaseTool\n\n\n"
        "class Hello(BaseTool):\n"
        '    name = "hello"\n'
        '    description = "向用户问好"\n\n'
        "    def execute(self, **kwargs):\n"
        '        return "你好！"\n\n\n'
        "def tools():\n"
        "    return [Hello()]\n",
        encoding="utf-8",
    )
    console.print(f"[green]已生成示例插件[/green] {directory}")
    console.print("[dim]默认是停用状态，检查无误后用 `xinbot plugin enable "
                f"{name}` 启用。[/dim]")


@plugin_app.command("template")
def template():
    """打印插件文件格式。"""
    console.print(SAMPLE, markup=False, highlight=False)
