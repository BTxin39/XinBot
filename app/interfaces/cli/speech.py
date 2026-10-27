"""`xinbot speech` —— 语音输出开关与试听。

语音是"陪衬"功能：默认关闭，且任何失败都不能影响聊天。
"""

from pathlib import Path

import typer
from rich.console import Console

speech_app = typer.Typer(help="语音输出（TTS）开关与试听。")
console = Console()


def _service():
    from app.services import speech_service

    return speech_service.service()


def _save(service) -> None:
    from app.paths import repo_root
    from app.services import speech_service

    speech_service.save_config(repo_root(), service.config)


@speech_app.callback(invoke_without_command=True)
def speech(ctx: typer.Context):
    """不带子命令时显示当前状态。"""
    if ctx.invoked_subcommand is not None:
        return
    status()


@speech_app.command("status")
def status():
    """查看语音状态（是否可用、引擎、语速、音量）。"""
    service = _service()
    info = service.status()
    available = "[green]可用[/green]" if info["available"] else "[yellow]不可用[/yellow]"
    enabled = "[green]已开启[/green]" if info["enabled"] else "[dim]已关闭[/dim]"
    console.print(f"语音输出：{enabled}｜引擎 {info['backend']}｜{available}")
    console.print(f"语速 {info['rate']}｜音量 {info['volume']}｜已朗读 {info['spoken']} 条")
    if not info["available"]:
        console.print(
            "[yellow]提示：[/yellow]未检测到可用的系统语音。"
            "Windows 可在「设置 → 时间和语言 → 语音」里安装中文语音包。"
        )


@speech_app.command("on")
def enable():
    """开启语音输出（之后每条新回复都会被朗读）。"""
    service = _service()
    if not service.available:
        console.print("[red]当前系统没有可用的语音引擎，无法开启。[/red]")
        raise typer.Exit(1)
    service.update_config(enabled=True)
    _save(service)
    console.print("[green]已开启语音输出[/green]")


@speech_app.command("off")
def disable():
    """关闭语音输出。"""
    service = _service()
    service.update_config(enabled=False)
    _save(service)
    console.print("已关闭语音输出")


@speech_app.command("rate")
def set_rate(value: int = typer.Argument(..., min=-10, max=10, help="-10（慢）~ 10（快），0 正常")):
    """调整语速。"""
    service = _service()
    config = service.update_config(rate=value)
    _save(service)
    console.print(f"语速已设为 {config.rate}")


@speech_app.command("volume")
def set_volume(value: int = typer.Argument(..., min=0, max=100)):
    """调整音量。"""
    service = _service()
    config = service.update_config(volume=value)
    _save(service)
    console.print(f"音量已设为 {config.volume}")


@speech_app.command("test")
def test(text: str = typer.Argument("你好，我是 XinBot。", help="要朗读的文本")):
    """试听一句（不会改变开关状态）。"""
    service = _service()
    if not service.available:
        console.print("[red]当前系统没有可用的语音引擎。[/red]")
        raise typer.Exit(1)
    # force=True：不依赖开关状态，也不会改它
    service.say(text, force=True)
    console.print("[green]已播放[/green]（开关状态未改变）")
