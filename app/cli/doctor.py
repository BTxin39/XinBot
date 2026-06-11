from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from app.config.runtime import CONFIG_PATH, RuntimeConfig
from app.config.cli_ui_settings import UI_SETTINGS_PATH, UISettings
from app.config.validation import ConfigValidator
from app.llm.registry import LLMRegistry, REGISTRY_PATH
from app.memory.chat_memory import ChatMemory


doctor_app = typer.Typer()
console = Console()


@doctor_app.callback(invoke_without_command=True)
def doctor():
    config = RuntimeConfig.load()
    registry = LLMRegistry()
    ui_settings = UISettings.load()
    validator = ConfigValidator()
    errors = validator.validate_startup_config(config)

    table = Table(title="XinBot Doctor")
    table.add_column("Check", style="cyan")
    table.add_column("Status")
    table.add_column("Detail")

    _add_path_check(table, "Runtime config", CONFIG_PATH)
    _add_path_check(table, "LLM registry", REGISTRY_PATH)
    _add_path_check(table, "UI settings", UI_SETTINGS_PATH)
    _add_path_check(
        table,
        "Prompt template",
        Path("app/llm/prompts/templates/system.txt"),
    )

    provider = registry.get_provider(config.provider)
    table.add_row(
        "Active provider",
        _ok(provider is not None),
        config.provider,
    )

    model = registry.get_model(config.model_name)
    table.add_row(
        "Active model",
        _ok(model is not None),
        config.model_name,
    )

    key_ready = provider is not None and bool(provider.api_key)
    table.add_row(
        "API key",
        _ok(key_ready),
        provider.api_key_env if provider else "unknown",
    )

    chat_memory = ChatMemory(config)
    table.add_row(
        "Current memory",
        _ok(config.current_memory_name in chat_memory.get_memory_list()),
        config.current_memory_name,
    )

    table.add_row(
        "History lines",
        _ok(ui_settings.history_display_lines >= 0),
        str(ui_settings.history_display_lines),
    )

    console.print(table)

    if errors:
        console.print("[bold red]Problems:[/bold red]")
        for error in errors:
            console.print(f"- {error}")
        raise typer.Exit(code=1)

    console.print("[bold green]Doctor check passed.[/bold green]")


def _add_path_check(table: Table, name: str, path: Path) -> None:
    table.add_row(
        name,
        _ok(path.exists()),
        str(path),
    )


def _ok(condition: bool) -> str:
    return "[green]OK[/green]" if condition else "[red]FAIL[/red]"
