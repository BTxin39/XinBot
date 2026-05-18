from rich.console import Console
from app.agent.agent import Agent
from app.commands.handler import CommandHandler
import typer

chat_app = typer.Typer()
console = Console()
# DEPRECATED
def start_chat():
    agent = Agent()

    command_handler = CommandHandler(agent)

    console.print(
        "[bold green]XinBot started![/bold green]"
    )

    while True:
        user_input = input("\nYou >> ")
        if user_input.lower() in ["exit", "quit"]:
            break
        handled = command_handler.handle(
            user_input
        )
        if handled:
            continue
        # response = agent.chat(user_input)
        # if user_input.startswith("/"):
        #     emotion = user_input.replace("/","")
        #     agent.state.emotion = emotion
        #     console.print(f"[yellow]Emotion changed to {emotion}[/yellow]")
        #     continue
        console.print(
            f"\n[bold green]XinBot >> [/bold green]", end=""
        )
        for chunk in agent.stream_chat(
            user_input=user_input
        ):
            print(chunk, end='', flush=True)
        print()

@chat_app.command()
def start(
    model: str | None = typer.Option(
        None,
        "--model",
        "-m",
        help="Override model for this chat session.",
    ),
    provider: str | None = typer.Option(
        None,
        "--provider",
        "-p",
        help="Override provider for this chat session.",
    ),
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

    agent = Agent(config)
    console.print(
        (
            "[bold green]XinBot started![/bold green] "
            f"[dim]provider={config.provider} "
            f"model={config.model_name}[/dim]"
        )
    )
    command_handler = CommandHandler(agent)
    while True:
        user_input = input("\nYou >> ")
        if user_input.lower() in ["exit", "quit"]:
            break
        handled = command_handler.handle(
            user_input
        )
        if handled:
            continue
        
        console.print(
            f"\n[bold green]XinBot >> [/bold green]", end=""
        )
        for chunk in agent.stream_chat(
            user_input=user_input
        ):
            print(chunk, end='', flush=True)
        print()
