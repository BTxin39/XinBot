from rich.console import Console
from rich.live import Live
import typer

from app.core.agent import Agent
from app.cli.desktop_ui import DesktopPetUI
from app.commands.handler import CommandHandler
from app.config.validation import validate_config

console = Console()
start_app = typer.Typer()


def run_cli(
    model: str | None = None,
    provider: str | None = None,
):
    from app.config.runtime import RuntimeConfig
    from app.llm.registry import LLMRegistry

    config = RuntimeConfig.load()
    if model:
        config.model_name = model
        registered_model = LLMRegistry().get_model(model)
        if registered_model and not provider:
            config.provider = registered_model.provider
    if provider:
        config.provider = provider

    validate_config(config)

    agent = Agent(config)
    command_handler = CommandHandler(agent)
    ui = DesktopPetUI(console)
    latest_reply: str | None = None

    while True:
        ui.render(agent, latest_reply)
        user_input = console.input("[bold yellow]You: [/bold yellow]")
        if user_input.lower() in ["exit", "quit"]:
            break

        handled = command_handler.handle(user_input)
        if handled:
            latest_reply = "命令已处理。"
            continue

        full_response = ""
        console.clear()
        with Live(
            ui.build_streaming_view(
                agent,
                "思考中...",
                current_input=user_input,
            ),
            console=console,
            refresh_per_second=10,
            transient=True,
        ) as live:
            for chunk in agent.stream_chat(user_input=user_input):
                full_response += chunk
                live.update(
                    ui.build_streaming_view(
                        agent,
                        full_response,
                        current_input=user_input,
                    )
                )

        latest_reply = full_response
        ui.render(agent, latest_reply, current_input=user_input)


@start_app.callback(invoke_without_command=True)
def cli(
    ctx: typer.Context,
    model: str | None = typer.Option(
        None, "--model", "-m", help="Override model for this chat session."
    ),
    provider: str | None = typer.Option(
        None, "--provider", "-p", help="Override provider for this chat session."
    ),
):
    if ctx.invoked_subcommand is not None:
        return
    run_cli(model=model, provider=provider)


@start_app.command()
def fastapi():
    pass


@start_app.command()
def live_2d():
    pass
