import typer
from rich.console import Console
from rich.markup import escape

from app.config.runtime import RuntimeConfig
from app.config.ui_settings import UISettings
from app.config.validation import validate_config
from app.llm.providers.factory import (
    list_provider_types,
    list_providers,
)
from app.llm.registry import (
    LLMRegistry,
    ModelConfig,
    ProviderConfig,
)

config_app = typer.Typer()
console = Console()


@config_app.command("show")
def show_config():
    config = RuntimeConfig.load()
    console.print(f"""
[bold green]Runtime Config[/bold green]

Provider: {config.provider}
Model: {config.model_name}
Temperature: {config.temperature}
Memory Limit: {config.max_memory_messages}
Current Memory Name: {config.current_memory_name}
""")


@config_app.command("ui-show")
def show_ui_config():
    settings = UISettings.load()
    console.print(f"""
[bold green]UI Settings[/bold green]

History Display Lines: {settings.history_display_lines}
""")
    for emotion, picture in settings.emotion_pictures.items():
        console.print(f"{emotion}: {escape(picture)}")


@config_app.command("ui-history-lines")
def set_ui_history_lines(lines: int):
    if lines < 0:
        console.print("[red]History lines must be >= 0[/red]")
        raise typer.Exit(code=1)

    settings = UISettings.load()
    settings.history_display_lines = lines
    settings.save()
    console.print(
        f"[green]History display lines set to {lines}[/green]"
    )


@config_app.command("ui-picture")
def set_ui_picture(
    emotion: str,
    picture: str = typer.Argument(
        ...,
        help="Picture placeholder, for example [picture_happy].",
    ),
):
    settings = UISettings.load()
    settings.emotion_pictures[emotion] = picture
    settings.save()
    console.print(
        (
            f"[green]Picture for {emotion} set to "
            f"{escape(picture)}[/green]"
        )
    )


@config_app.command("set-model")
def set_model(model_name: str):
    registry = LLMRegistry()
    model = registry.get_model(model_name)
    if model is None:
        console.print(
            f"[red]Unknown model:[/red] {model_name}"
        )
        console.print(
            "[yellow]Use `xinbot config add-model` first.[/yellow]"
        )
        raise typer.Exit(code=1)

    config = RuntimeConfig.load()
    config.model_name = model_name
    config.provider = model.provider
    # 验证配置的有效性
    try:
        validate_config(config)
    except ValueError:
        console.print(
            f"[red]Configuration would be invalid with model {model_name}.[/red]"
        )
        raise typer.Exit(code=1)
    
    config.save()
    console.print(
        (
            f"[green]Model set to {model_name}[/green] "
            f"[dim]provider={model.provider}[/dim]"
        )
    )


@config_app.command("set-provider")
def set_provider(provider_name: str):
    providers = list_providers()
    if provider_name not in providers:
        supported = ", ".join(providers)
        console.print(
            f"[red]Unsupported provider:[/red] {provider_name}"
        )
        console.print(
            f"[yellow]Supported providers:[/yellow] {supported}"
        )
        raise typer.Exit(code=1)

    config = RuntimeConfig.load()
    config.provider = provider_name
    # 验证配置的有效性
    try:
        validate_config(config)
    except ValueError:
        console.print(
            f"[red]Configuration would be invalid with provider {provider_name}.[/red]"
        )
        raise typer.Exit(code=1)
    
    config.save()
    console.print(
        f"[green]Provider set to {provider_name}[/green]"
    )


@config_app.command("providers")
def providers():
    registry = LLMRegistry()
    for provider in registry.list_providers():
        console.print(
            f"{provider.name} "
            f"[dim]type={provider.provider_type} "
            f"api_key_env={provider.api_key_env} "
            f"base_url={provider.base_url} "
            f"base_url_env={provider.base_url_env}[/dim]"
        )


@config_app.command("provider-types")
def provider_types():
    for provider_type in list_provider_types():
        console.print(provider_type)


@config_app.command("add-provider")
def add_provider(
    name: str,
    provider_type: str = typer.Option(
        "openai-compatible",
        "--type",
        help="Provider implementation type.",
    ),
    api_key_env: str = typer.Option(
        ...,
        "--api_key_env",
        help="Environment variable that stores the API key.",
    ),
    base_url_env: str | None = typer.Option(
        None,
        "--base_url_env",
        help="Environment variable that stores the base URL.",
    ),
    base_url: str | None = typer.Option(
        None,
        "--base_url",
        help="Base URL for OpenAI-compatible providers.",
    ),
):
    if provider_type not in list_provider_types():
        supported = ", ".join(list_provider_types())
        console.print(
            f"[red]Unsupported provider type:[/red] {provider_type}"
        )
        console.print(
            f"[yellow]Supported types:[/yellow] {supported}"
        )
        raise typer.Exit(code=1)

    registry = LLMRegistry()
    try:
        registry.add_provider(
            ProviderConfig(
                name=name,
                provider_type=provider_type,
                api_key_env=api_key_env,
                base_url=base_url,
                base_url_env=base_url_env,
            )
        )
    except ValueError as error:
        console.print(f"[red]{error}[/red]")
        raise typer.Exit(code=1)

    console.print(
        f"[green]Provider added:[/green] {name}"
    )


@config_app.command("remove-provider")
def remove_provider(name: str):
    registry = LLMRegistry()
    config = RuntimeConfig.load()
    if config.provider == name:
        console.print(
            "[red]Cannot remove active provider.[/red]"
        )
        console.print(
            "[yellow]Switch provider first with "
            "`xinbot config set-provider`.[/yellow]"
        )
        raise typer.Exit(code=1)

    try:
        registry.remove_provider(name)
    except ValueError as error:
        console.print(f"[red]{error}[/red]")
        raise typer.Exit(code=1)

    console.print(
        f"[green]Provider removed:[/green] {name}"
    )


@config_app.command("models")
def models():
    registry = LLMRegistry()
    for model in registry.list_models():
        console.print(
            f"{model.name} [dim]provider={model.provider}[/dim]"
        )


@config_app.command("add-model")
def add_model(
    name: str,
    provider: str = typer.Option(
        ...,
        "--provider",
        "-p",
        help="Provider that serves this model.",
    ),
):
    registry = LLMRegistry()
    try:
        registry.add_model(
            ModelConfig(
                name=name,
                provider=provider,
            )
        )
    except ValueError as error:
        console.print(f"[red]{error}[/red]")
        raise typer.Exit(code=1)

    console.print(
        f"[green]Model added:[/green] {name}"
    )


@config_app.command("remove-model")
def remove_model(name: str):
    config = RuntimeConfig.load()
    if config.model_name == name:
        console.print(
            "[red]Cannot remove active model.[/red]"
        )
        console.print(
            "[yellow]Switch model first with "
            "`xinbot config set-model`.[/yellow]"
        )
        raise typer.Exit(code=1)

    LLMRegistry().remove_model(name)
    console.print(
        f"[green]Model removed:[/green] {name}"
    )
