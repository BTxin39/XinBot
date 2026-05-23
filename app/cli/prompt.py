from rich.console import Console
from rich.table import Table
import typer
from pathlib import Path
from app.llm.prompts.prompt_builder import PromptTemplate

prompt_app = typer.Typer()
console = Console()

@prompt_app.command()
def list():
    """列出所有可用的提示词模板"""
    template_manager = PromptTemplate()
    
    table = Table(title="Prompt Templates")
    table.add_column("Name", style="cyan", no_wrap=True)
    table.add_column("Content Preview", style="magenta")
    
    # 显示内置模板
    templates = template_manager.get_template("emotions")
    table.add_row("system", template_manager.get_template("system")[:50] + "...")
    
    for emotion, prompt in templates.items():
        table.add_row(f"emotion_{emotion}", prompt)
    
    # 显示文件模板
    templates_dir = Path("app/llm/prompts/templates")
    for file in templates_dir.glob("*.txt"):
        if file.name not in ["system.txt"]:  # 已显示过的跳过
            content_preview = file.read_text(encoding='utf-8')[:50] + "..."
            table.add_row(file.stem, content_preview)
    
    console.print(table)

@prompt_app.command()
def show(name: str):
    """显示指定提示词的内容"""
    template_manager = PromptTemplate()
    
    if name == "system":
        content = template_manager.get_template("system")
    elif name.startswith("emotion_"):
        emotions = template_manager.get_template("emotions")
        emotion_name = name.replace("emotion_", "")
        content = emotions.get(emotion_name, f"Emotion '{emotion_name}' not found")
    else:
        # 尝试从文件加载
        templates_dir = Path("app/llm/prompts/templates")
        file_path = templates_dir / f"{name}.txt"
        if file_path.exists():
            content = file_path.read_text(encoding='utf-8')
        else:
            console.print(f"[red]Template '{name}' not found[/red]")
            return
    
    console.print(f"[bold cyan]Template: {name}[/bold cyan]")
    console.print("=" * 50)
    console.print(content)

@prompt_app.command()
def edit(name: str, content: str = typer.Argument(..., help="New content for the prompt")):
    """编辑指定提示词的内容"""
    template_manager = PromptTemplate()
    template_manager.update_template(name, content)
    console.print(f"[green]Template '{name}' updated successfully![/green]")

@prompt_app.command()
def reset(name: str):
    """重置指定提示词到默认值"""
    template_manager = PromptTemplate()
    
    defaults = {
        "system": """你是一只 AI 桌宠。

你的名字叫 xin。

你会温柔、简短地和用户聊天。

你像一个真正陪伴用户的小桌宠。""",
        "emotions": {
            "normal": "你现在情绪平静。",
            "happy": "你现在很开心，说话更活泼。",
            "sad": "你现在有点失落，说话更轻柔。",
            "angry": "你现在有点闹脾气。",
            "sleepy": "你现在很困，说话慢一点。",
        }
    }
    
    if name == "system":
        template_manager.update_template(name, defaults["system"])
        console.print(f"[green]System template reset to default![/green]")
    elif name in defaults["emotions"]:
        template_manager.update_template("emotions", str(defaults["emotions"]))
        console.print(f"[green]Emotion template '{name}' reset![/green]")
    else:
        console.print(f"[red]Cannot reset template '{name}', not a built-in template[/red]")