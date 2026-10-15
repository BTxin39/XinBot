"""Debug 调试接口：纯文本流式对话，无 Rich UI。"""

import typer

from app.interfaces.cli.approval import cli_approval_callback
from app.interfaces.cli.session import runner_factory

debug_app = typer.Typer()


@debug_app.callback(invoke_without_command=True)
def debug(
    ctx: typer.Context,
    model: str | None = typer.Option(
        None, "--model", "-m", help="Override model for this session."
    ),
    provider: str | None = typer.Option(
        None, "--provider", "-p", help="Override provider for this session."
    ),
):
    """启动纯文本调试对话（无 Rich UI）。"""
    if ctx.invoked_subcommand is not None:
        return

    from app.config.runtime import RuntimeConfig
    from app.llm.registry import LLMRegistry
    from app.config.validation import ConfigValidationError, validate_config

    config = RuntimeConfig.load()
    if model:
        config.model_name = model
        registered_model = LLMRegistry().get_model(model)
        if registered_model and not provider:
            config.provider = registered_model.provider
    if provider:
        config.provider = provider

    try:
        validate_config(config)
    except ConfigValidationError as error:
        print("配置校验失败：")
        for reason in error.errors:
            print(f"  - {reason}")
        raise typer.Exit(code=1)

    runner = runner_factory(config, approval_callback=cli_approval_callback)
    runner.init()

    print(f"\nXinBot debug | provider={config.provider} model={config.model_name}")
    print("输入内容开始对话，输入 exit / quit 退出。\n")

    while True:
        try:
            user_input = input(">>> ")
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if user_input.lower() in ("exit", "quit"):
            break

        if runner.handle_command(user_input):
            continue

        for chunk in runner.chat_once(user_input=user_input):
            print(chunk, end="", flush=True)
        print()

    result = runner.shutdown()
    print(f"\n{result}")
