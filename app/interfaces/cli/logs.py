"""xinbot logs —— 查看后端运行状态与运行日志。

日志来源是**后端进程的内存缓冲**。CLI 是独立进程，因此经 `/api/logs` 拉取；
后端未运行时明确提示，避免"空列表"被误读成"没有日志"。
"""

import time
from pathlib import Path

import httpx
import typer
from rich.console import Console

from app.config.runtime import RuntimeConfig

logs_app = typer.Typer()
console = Console()

LEVEL_STYLES = {
    "DEBUG": "dim",
    "INFO": "green",
    "WARNING": "yellow",
    "ERROR": "red",
    "CRITICAL": "bold red",
}


def _base_url() -> str:
    return f"http://127.0.0.1:{RuntimeConfig.load().web_port}"


def _fetch(limit: int, level: str | None) -> tuple[dict, list[dict]]:
    """拉取后端日志；失败时抛出 typer.Exit 并给出可操作的提示。"""
    url = _base_url() + "/api/logs"
    params = {"limit": limit}
    if level:
        params["level"] = level
    try:
        with httpx.Client(trust_env=False, timeout=5) as client:
            response = client.get(url, params=params)
            response.raise_for_status()
            payload = response.json()
    except (httpx.HTTPError, ValueError) as error:
        console.print(f"[red]读取后端日志失败：[/red]{error}")
        console.print(
            f"[yellow]后端可能未运行。[/yellow]先执行 `xinbot start web`，"
            f"或用 `xinbot start --show` 查询状态（预期地址 {_base_url()}）。"
        )
        raise typer.Exit(code=1) from error
    data = payload.get("data") or {}
    return data.get("status") or {}, data.get("entries") or []


def _print_entries(entries: list[dict]) -> None:
    if not entries:
        console.print("[dim]暂无日志。[/dim]")
        return
    for item in entries:
        style = LEVEL_STYLES.get(item["level"], "white")
        console.print(
            f"[dim]{item['stamp']}[/dim] [{style}]{item['level']:<7}[/{style}] "
            f"[cyan]{item['logger']}[/cyan] {item['message']}"
        )


def _print_status(status: dict) -> None:
    uptime = status.get("uptime_seconds") or 0
    minutes, seconds = divmod(int(uptime), 60)
    console.print(
        f"[bold]后端运行状态[/bold]  已运行 [green]{minutes}分{seconds}秒[/green]  "
        f"缓冲 [cyan]{status.get('buffered', 0)}/{status.get('capacity', 0)}[/cyan]  "
        f"警告 [yellow]{status.get('warnings', 0)}[/yellow]  "
        f"错误 [red]{status.get('errors', 0)}[/red]"
    )


@logs_app.callback(invoke_without_command=True)
def logs(
    ctx: typer.Context,
    limit: int = typer.Option(40, "--limit", "-n", min=1, max=500, help="显示最近多少条"),
    level: str | None = typer.Option(None, "--level", "-l", help="最低级别：DEBUG/INFO/WARNING/ERROR"),
    follow: bool = typer.Option(False, "--follow", "-f", help="持续跟踪（Ctrl+C 退出）"),
):
    """查看后端运行状态与最近日志。"""
    if ctx.invoked_subcommand is not None:
        return

    status, entries = _fetch(limit, level)
    _print_status(status)
    _print_entries(entries)

    if not follow:
        return

    seen = {(item["time"], item["message"]) for item in entries}
    console.print("[dim]── 跟踪中，Ctrl+C 退出 ──[/dim]")
    try:
        while True:
            time.sleep(1.5)
            status, entries = _fetch(limit, level)
            for item in entries:
                key = (item["time"], item["message"])
                if key in seen:
                    continue
                seen.add(key)
                _print_entries([item])
    except KeyboardInterrupt:
        console.print("\n[dim]已停止跟踪。[/dim]")


@logs_app.command("status")
def status_only():
    """只显示运行状态摘要。"""
    status, _ = _fetch(1, None)
    _print_status(status)


@logs_app.command("export")
def export_logs(
    output: str = typer.Option("xinbot-logs.log", "--out", "-o", help="保存路径"),
    limit: int = typer.Option(500, "--limit", "-n", min=1, max=500, help="导出最近多少条"),
    level: str | None = typer.Option(None, "--level", "-l", help="最低级别过滤"),
):
    """把后端最近日志导出为文本文件（含完整日期与表头，便于归档）。"""
    params = {"limit": limit}
    if level:
        params["level"] = level
    url = _base_url() + "/api/logs/export"
    try:
        with httpx.Client(trust_env=False, timeout=10) as client:
            response = client.get(url, params=params)
            response.raise_for_status()
            text = response.text
    except (httpx.HTTPError, ValueError) as error:
        console.print(f"[red]导出失败：[/red]{error}")
        console.print(
            f"[yellow]后端可能未运行。[/yellow]先执行 `xinbot start web`（预期地址 {_base_url()}）。"
        )
        raise typer.Exit(code=1) from error

    target = Path(output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    lines = sum(1 for line in text.splitlines() if line and not line.startswith("#"))
    console.print(f"[green]✓ 已导出[/green] {lines} 条日志 → {target.resolve()}")


@logs_app.command("clear")
def clear_logs():
    """清空后端日志缓冲。"""
    try:
        with httpx.Client(trust_env=False, timeout=5) as client:
            response = client.delete(_base_url() + "/api/logs")
            response.raise_for_status()
    except (httpx.HTTPError, ValueError) as error:
        console.print(f"[red]清空失败：[/red]{error}")
        raise typer.Exit(code=1) from error
    console.print("[green]已清空后端日志缓冲。[/green]")
