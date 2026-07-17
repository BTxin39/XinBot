"""xinbot rag —— 本地知识库管理。"""

from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from app.rag.document import KnowledgeBase

rag_app = typer.Typer()
console = Console()


def _get_kb() -> KnowledgeBase:
    """懒加载 KnowledgeBase。"""
    return KnowledgeBase()


@rag_app.command("ingest")
def ingest(
    path: str = typer.Argument(..., help="文件或目录路径"),
):
    """导入文件或整个目录到知识库。"""
    kb = _get_kb()
    p = Path(path)

    if not p.exists():
        console.print(f"[red]路径不存在: {path}[/red]")
        raise typer.Exit(code=1)

    if p.is_file():
        result = kb.ingest_file(p)
        if result["status"] == "ok":
            console.print(f"[green]✓[/green] {result['file']} → {result['chunks']} 个分块")
        else:
            console.print(f"[yellow]⊘[/yellow] {result['file']}: {result['status']}")
    elif p.is_dir():
        results = kb.ingest_directory(p)
        ok_count = sum(1 for r in results if r["status"] == "ok")
        total_chunks = sum(r["chunks"] for r in results if r["status"] == "ok")
        console.print(f"[green]已导入 {ok_count}/{len(results)} 个文件，共 {total_chunks} 个分块[/green]")
        for r in results:
            if r["status"] != "ok":
                console.print(f"  [yellow]⊘[/yellow] {r['file']}: {r['status']}")


@rag_app.command("ingest-url")
def ingest_url(
    url: str = typer.Argument(..., help="网页 URL"),
):
    """导入网页内容到知识库。"""
    kb = _get_kb()
    console.print(f"[dim]正在下载: {url}...[/dim]")
    result = kb.ingest_url(url)
    if result["status"] == "ok":
        console.print(f"[green]✓[/green] {result['chunks']} 个分块已导入")
    else:
        console.print(f"[red]✗[/red] {result['status']}")


@rag_app.command("search")
def search(
    query: str = typer.Argument(..., help="搜索查询"),
    k: int = typer.Option(5, "--top", "-k", help="返回结果数"),
):
    """搜索知识库。"""
    kb = _get_kb()
    results = kb.search(query, k=k)

    if not results:
        console.print("[dim]知识库为空或未找到相关结果。[/dim]")
        return

    for i, r in enumerate(results, 1):
        source = r["source"]
        text_preview = r["text"][:200].replace("\n", " ")
        console.print(f"[bold cyan]#{i}[/bold cyan] [{source}]")
        console.print(f"  {text_preview}...")
        console.print()


@rag_app.command("list")
def list_sources():
    """列出知识库中所有来源。"""
    kb = _get_kb()
    sources = kb.list_sources()

    if not sources:
        console.print("[dim]知识库为空。[/dim]")
        return

    table = Table(title="Knowledge Base Sources")
    table.add_column("Source", style="cyan")
    table.add_column("Chunks", justify="right")

    total = 0
    for s in sources:
        table.add_row(s["source"], str(s["chunks"]))
        total += s["chunks"]

    console.print(table)
    console.print(f"[dim]共 {len(sources)} 个来源，{total} 个分块[/dim]")


@rag_app.command("remove")
def remove_source(
    source: str = typer.Argument(..., help="来源路径（与 list 命令显示的一致）"),
):
    """从知识库中删除指定来源。"""
    kb = _get_kb()
    count = kb.remove_source(source)
    if count > 0:
        console.print(f"[green]已删除 {count} 个分块[/green]")
    else:
        console.print(f"[yellow]未找到来源: {source}[/yellow]")


@rag_app.command("stats")
def stats():
    """显示知识库统计信息。"""
    kb = _get_kb()
    s = kb.store.stats()
    sources = kb.list_sources()
    console.print(f"[bold]知识库统计[/bold]")
    console.print(f"  来源数: {len(sources)}")
    console.print(f"  分块总数: {s['total_chunks']}")
    console.print(f"  Collection: {s['collection_name']}")


@rag_app.command("clear")
def clear(
    force: bool = typer.Option(False, "--force", "-f", help="跳过确认"),
):
    """清空整个知识库。"""
    if not force:
        confirm = typer.confirm("确认清空整个知识库？此操作不可撤销。")
        if not confirm:
            console.print("[dim]已取消。[/dim]")
            return

    kb = _get_kb()
    kb.clear()
    console.print("[green]知识库已清空。[/green]")
