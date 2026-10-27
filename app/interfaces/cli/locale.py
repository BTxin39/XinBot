"""`xinbot locale` —— 界面语言。

网页端在「设置」里也能切，这里给纯命令行用户一个入口。

命令形态：
    xinbot locale            # 显示当前语言
    xinbot locale status     # 同上（显式子命令）
    xinbot locale set en     # 切换

为什么不做 `xinbot locale en` 这种简写：Typer 的子命令组会把 `en` 当成
未知子命令并直接退出（exit 2），拿不到 `ctx.args`。简写省不了几个字符，
却多一条容易踩的路径，所以只保留 `set`。
"""

import typer
from rich.console import Console

from app.services import i18n_service

locale_app = typer.Typer(help="查看 / 切换界面语言。")
console = Console()


def _root():
    from app.paths import repo_root

    return repo_root()


@locale_app.callback(invoke_without_command=True)
def locale(ctx: typer.Context):
    if ctx.invoked_subcommand is not None:
        return
    status()


@locale_app.command("status")
def status():
    """显示当前语言与可选语言。"""
    current = i18n_service.load(_root())
    options = "、".join(f"{item['code']}（{item['label']}）" for item in i18n_service.available())
    console.print(f"当前语言：{current}")
    console.print(f"可选：{options}")


@locale_app.command("set")
def set_command(value: str = typer.Argument(..., help="语言代码，如 en")):
    """切换语言。"""
    change(value)


def _supported(raw: str) -> bool:
    """用户输入是否指向受支持的语言（允许 `en-US` 这种地区写法）。"""
    text = (raw or "").strip().replace("_", "-").lower()
    if not text:
        return False
    known = {code.lower() for code in i18n_service.LOCALES}
    bases = {code.split("-")[0].lower() for code in i18n_service.LOCALES}
    return text in known or text.split("-")[0] in bases


def change(value: str) -> None:
    saved = i18n_service.save(_root(), value)
    # 不能用 normalize(value) 和 saved 比较——两者都会把 fr 变成 zh-CN，
    # 那样永远"相等"，回落就静默了。
    if not _supported(value):
        console.print(f"[yellow]不支持的语言 {value!r}，已回落为 {saved}[/yellow]")
    else:
        console.print(f"[green]已切换为[/green] {saved}")
    console.print("[dim]影响：网页端界面与桌宠的问候语（下次启动生效）。[/dim]")
