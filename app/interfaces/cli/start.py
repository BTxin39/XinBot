"""xinbot start —— 启动桌面宠物 CLI。

子命令:
    cli        → 终端 Rich UI 桌面宠物
    web        → FastAPI Web 后端 + (可选) Pygame 桌面宠
"""

import typer

from app.interfaces.cli.approval import cli_approval_callback
from app.interfaces.cli.desktop_ui import DesktopPetUI
from app.services.image_ascii import image_to_braille
from app.interfaces.cli.session import runner_factory

start_app = typer.Typer(no_args_is_help=True)


@start_app.callback(invoke_without_command=True)
def start(ctx: typer.Context, show: bool = typer.Option(False, "--show", help="查询网页后端运行状态")):
    if show:
        from app.interfaces.web.process import show as show_status
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
    from app.interfaces.cli.ui_settings import UISettings
    from app.llm.registry import LLMRegistry
    from app.config.validation import ConfigValidationError, validate_config

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

    try:
        validate_config(config)
    except ConfigValidationError as error:
        console.print("[red]配置校验失败：[/red]")
        for reason in error.errors:
            console.print(f"  [red]-[/red] {reason}")
        raise typer.Exit(code=1)

    runner = runner_factory(config, approval_callback=cli_approval_callback)
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
    port: int | None = typer.Option(None, "--port", "-p", min=1024, max=65535, help="Web 端口，默认 3796；已保存配置时使用配置值"),
):
    """启动 FastAPI Web 后端 (REST + WebSocket)。

    开发模式:
        xinbot start web --dev

    生产模式 (serve 前端 build 产物):
        xinbot start web
    """
    from app.config.runtime import RuntimeConfig
    from app.interfaces.web.process import launch, shutdown as stop_server
    try:
        if shutdown:
            stop_server()
            return
        launch(port or RuntimeConfig.load().web_port, dev=dev)
    except (RuntimeError, OSError) as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(1)


@start_app.command(help="启动桌面常驻桌宠（透明 / 置顶 / 可鼠标穿透）。")
def pet(
    no_passthrough: bool = typer.Option(
        False, "--no-passthrough",
        help="关闭默认鼠标穿透：桌宠会挡住桌面点击（调试时用）",
    ),
    no_topmost: bool = typer.Option(
        False, "--no-topmost", help="不置顶，允许其他窗口盖住桌宠"
    ),
    no_tray: bool = typer.Option(
        False, "--no-tray", help="不显示系统托盘图标"
    ),
    port: int | None = typer.Option(
        None, "--port", "-p", min=1024, max=65535, help="后端端口（默认读保存的配置）"
    ),
    autostart_launch: bool = typer.Option(
        False, "--autostart-launch", hidden=True,
        help="内部参数：由开机自启项传入，表示无人值守启动",
    ),
    autostart: str | None = typer.Option(
        None, "--autostart", help="开机自启：on / off / status（不启动窗口）"
    ),
):
    """启动桌面常驻桌宠。

    需要后端在跑：本命令会检测，未运行则自动启动。

        xinbot start pet                    # 透明+置顶+穿透+托盘
        xinbot start pet --no-passthrough   # 不穿透（能直接点桌宠）
        xinbot start pet --no-tray          # 不起托盘图标
        xinbot start pet --autostart on     # 开机自启（不启动窗口）
    """
    import typer as _typer

    from app.config.runtime import RuntimeConfig
    from app.interfaces.desktop import autostart as autostart_module
    from app.interfaces.desktop import shell, win32_api
    from app.paths import repo_root

    if not win32_api.available():
        _typer.echo("桌宠窗口目前仅支持 Windows。", err=True)
        raise _typer.Exit(1)

    # 只管理开机自启，不启动窗口
    if autostart is not None:
        manager = autostart_module.Autostart()
        mode = autostart.lower()
        if mode == "status":
            entry = manager.status()
            if entry:
                _typer.echo(f"开机自启：已开启\n命令：{entry.command}")
            else:
                _typer.echo("开机自启：未开启")
            return
        if mode == "on":
            command = autostart_module.Autostart.default_command(repo_root())
            manager.enable(command)
            _typer.echo(f"已开启开机自启：{command}")
            return
        if mode == "off":
            removed = manager.disable()
            _typer.echo("已关闭开机自启" if removed else "开机自启本来就是关闭状态")
            return
        _typer.echo("--autostart 只接受 on / off / status", err=True)
        raise _typer.Exit(2)

    config = RuntimeConfig.load()
    actual_port = port or config.web_port

    # 复用网页后端的受管进程逻辑：未运行则拉起
    from app.interfaces.web.process import ensure_running

    try:
        ensure_running(actual_port)
    except (RuntimeError, OSError) as error:
        _typer.echo(f"后端启动失败：{error}", err=True)
        raise _typer.Exit(1) from error

    url = f"http://127.0.0.1:{actual_port}/#/pet"
    try:
        shell.run(
            url,
            repo_root(),
            click_through=not no_passthrough,
            always_on_top=not no_topmost,
            with_tray=not no_tray,
        )
    except RuntimeError as error:
        _typer.echo(str(error), err=True)
        raise _typer.Exit(1) from error

