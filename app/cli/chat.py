from rich.console import Console
from app.core.agent import Agent
from app.commands.handler import CommandHandler
from app.config.validation import validate_config
import typer

chat_app = typer.Typer()
console = Console()

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

    # 在创建Agent之前进行配置验证
    validate_config(config)

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
            console.print("\n[yellow]正在保存记忆...[/yellow]")
            try:
                result = agent.remember_now()
                console.print(f"[dim]{result}[/dim]")
            except Exception as e:
                console.print(f"[yellow]记忆保存失败: {e}[/yellow]")
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