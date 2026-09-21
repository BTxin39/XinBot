"""xinbot start —— 启动桌面宠物 CLI。

子命令:
    cli        → 终端 Rich UI 桌面宠物
    web        → FastAPI Web 后端 + (可选) Pygame 桌面宠
"""

import typer

from app.core.agent import Agent
from app.core.session import SessionRunner
from app.cli.desktop_ui import DesktopPetUI
from app.cli.image_to_ascii import image_to_braille

start_app = typer.Typer(no_args_is_help=True)


@start_app.callback(invoke_without_command=True)
def start(ctx: typer.Context, show: bool = typer.Option(False, "--show", help="查询网页后端运行状态")):
    if show:
        from app.web.process import show as show_status
        show_status()
        raise typer.Exit()
    if ctx.invoked_subcommand is None:
        print(ctx.get_help())


def run_cli(
    model: str | None = None,
    provider: str | None = None,
    image: str | None = None,
    image_width: int = 40,
):
    """启动终端桌面宠物（Rich UI）。"""
    from rich.console import Console
    from app.config.runtime import RuntimeConfig
    from app.config.cli_ui_settings import UISettings
    from app.llm.registry import LLMRegistry
    from app.config.validation import validate_config

    console = Console()
    config = RuntimeConfig.load()

    if model:
        config.model_name = model
        registered_model = LLMRegistry().get_model(model)
        if registered_model and not provider:
            config.provider = registered_model.provider
    if provider:
        config.provider = provider

    # 如果指定了 --image，转成 braille art 并写入 UI 设置
    if image:
        try:
            braille = image_to_braille(image, width=image_width)
        except ImportError as e:
            console.print(f"[yellow]{e}[/yellow]")
            return
        except FileNotFoundError as e:
            console.print(f"[red]{e}[/red]")
            return

        ui = UISettings.load()
        for emotion in ("normal", "happy", "sad", "angry", "sleepy"):
            ui.emotion_pictures[emotion] = braille
        ui.save()
        console.print(f"[green]图片已转换为 braille art（宽={image_width}字符）[/green]")

    validate_config(config)

    runner = SessionRunner(agent_factory=lambda: Agent(config))
    ui = DesktopPetUI(console)
    runner.run(ui)


@start_app.command()
def cli(
    ctx: typer.Context,
    model: str | None = typer.Option(
        None, "--model", "-m", help="Override model for this session."
    ),
    provider: str | None = typer.Option(
        None, "--provider", "-p", help="Override provider for this session."
    ),
    image: str | None = typer.Option(
        None, "--image", "-i", help="Convert image to braille art for the pet."
    ),
    image_width: int = typer.Option(
        40, "--image-width", help="Output width in characters (default: 40)."
    ),
):
    """启动 XinBot 桌面宠物 CLI。

    示例:
        xinbot start cli              # 启动（Q 版默认宠物）
        xinbot start cli -m gpt-4.1    # 指定模型
        xinbot start cli -i cat.png    # 用图片作为宠物图案
    """
    if ctx.invoked_subcommand is not None:
        return
    run_cli(model=model, provider=provider, image=image, image_width=image_width)


@start_app.command(help="启动网页桌宠（默认 http://127.0.0.1:3796）。")
def web(
    shutdown: bool = typer.Option(False, "--shutdown", help="关闭本项目启动的网页后端"),
    dev: bool = typer.Option(False, "--dev", help="开发模式，不 serve 前端静态文件"),
    no_pet: bool = typer.Option(True, "--no-pet", help="跳过 Pygame 桌面宠物子进程"),
    port: int | None = typer.Option(None, "--port", "-p", min=1024, max=65535, help="Web 端口，默认 3796；已保存配置时使用配置值"),
):
    """启动 FastAPI Web 后端 (REST + WebSocket)。

    开发模式:
        xinbot start web --dev

    生产模式 (serve 前端 build 产物):
        xinbot start web

    不启动桌面宠物:
        xinbot start web --no-pet
    """
    from app.config.runtime import RuntimeConfig
    from app.web.process import launch, shutdown as stop_server
    try:
        if shutdown:
            stop_server()
            return
        launch(port or RuntimeConfig.load().web_port, dev=dev)
    except (RuntimeError, OSError) as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(1)


@start_app.command(deprecated=True)
def fastapi():
    """(已废弃) 请使用 xinbot start web"""
    print("请使用 xinbot start web 代替 xinbot start fastapi")


@start_app.command(deprecated=True)
def live_2d():
    """(已废弃) Live2D 渲染已集成到 Web 前端"""
    print("Live2D 渲染已集成到 Web 前端，请使用 xinbot start web")
