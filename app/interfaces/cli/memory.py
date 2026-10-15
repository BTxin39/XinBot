from rich.console import Console
import typer

from app.memory.chat_memory import ChatMemory


memory_app = typer.Typer()
console = Console()

@memory_app.command()
def list():
    """List all available memory instances"""
    chat_memory = ChatMemory()
    memories = chat_memory.get_memory_list()
    if memories:
        console.print("[bold blue]Available Memories:[/bold blue]")
        for memory in memories:
            # 获取当前内存名称以标记活动状态
            current_memory = chat_memory.config.current_memory_name
            marker = " [bold green](current)[/bold green]" if memory == current_memory else ""
            description = chat_memory.get_memory_description(memory)
            console.print(f"- {memory}{marker}")
            if description:
                console.print(f"  Description: {description}")
    else:
        console.print("[yellow]No memories found.[/yellow]")

@memory_app.command()
def get(memory_name: str = typer.Option(None, "--name", "-n", help="Name of the memory to retrieve")):
    """Get messages from a specific memory"""
    chat_memory = ChatMemory()
    memory_name_to_use = memory_name
    if memory_name_to_use is None:
        memory_name_to_use = chat_memory.config.current_memory_name
    
    memories = chat_memory.get_memory_list()
    
    if memory_name_to_use not in memories:
        console.print(f"[red]Error: Memory '{memory_name_to_use}' does not exist.[/red]")
        return
    
    # 临时加载指定内存以获取消息
    temp_storage = chat_memory._get_or_create_memory(memory_name_to_use)
    data = temp_storage.load()
    messages = data.get("messages", [])
    
    if messages:
        console.print(f"[bold blue]Messages in '{memory_name_to_use}':[/bold blue]")
        for i, msg in enumerate(messages, 1):
            role = msg.get('role', 'unknown')
            content = msg.get('content', '')
            console.print(f"{i}. [{role}] {content}")
    else:
        console.print(f"[yellow]Memory '{memory_name_to_use}' is empty.[/yellow]")

@memory_app.command()
def clear(
    memory_name: str = typer.Option(None, "--name", "-n", help="Name of the memory to clear (default: current memory)")
):
    """Clear messages from a specific memory or current memory if not specified"""
    chat_memory = ChatMemory()
    
    if memory_name is None:
        # 清除当前内存，但保留描述
        current_desc = chat_memory.get_memory_description(chat_memory.config.current_memory_name)
        chat_memory.messages.clear()
        chat_memory.storage.save({
            "messages": [],
            "description": current_desc
        })
        console.print(f"[green]Current memory '{chat_memory.config.current_memory_name}' cleared (description preserved).[/green]")
    else:
        # 检查内存是否存在
        memories = chat_memory.get_memory_list()
        if memory_name not in memories:
            console.print(f"[red]Error: Memory '{memory_name}' does not exist.[/red]")
            return
        
        # 临时加载指定内存并清除，但保留描述
        temp_storage = chat_memory._get_or_create_memory(memory_name)
        current_desc = chat_memory.get_memory_description(memory_name)
        temp_storage.save({
            "messages": [],
            "description": current_desc
        })
        
        # 如果是当前内存，也更新实例
        if memory_name == chat_memory.config.current_memory_name:
            chat_memory.messages = []
        
        console.print(f"[green]Memory '{memory_name}' cleared (description preserved).[/green]")

@memory_app.command()
def switch(
    memory_name: str = typer.Option(..., "--name", "-n", help="Name of the memory to switch to")
):
    """Switch to a different memory instance"""
    chat_memory = ChatMemory()
    memories = chat_memory.get_memory_list()
    
    if memory_name not in memories:
        console.print(f"[red]Error: Memory '{memory_name}' does not exist.[/red]")
        console.print(f"[blue]Use 'xinbot memory list' to see available memories.[/blue]")
        return
    
    # 更新运行时配置中的当前内存名称
    chat_memory.config.current_memory_name = memory_name
    chat_memory.config.save()
    
    console.print(f"[green]Switched to memory: {memory_name}[/green]")

@memory_app.command()
def create(
    memory_name: str = typer.Option(..., "--name", "-n", help="Name of the new memory to create"),
    description: str = typer.Option("", "--desc", "-d", help="Description for the new memory")
):
    """Create a new memory instance"""
    chat_memory = ChatMemory()
    memories = chat_memory.get_memory_list()
    
    if memory_name in memories:
        console.print(f"[red]Error: Memory '{memory_name}' already exists.[/red]")
        return
    
    # 创建新的内存存储
    new_storage = chat_memory._get_or_create_memory(memory_name)
    
    # 如果提供了描述，则设置描述
    if description:
        chat_memory.set_memory_description(memory_name, description)
    
    console.print(f"[green]Created new memory: {memory_name}[/green]")

@memory_app.command()
def delete(
    memory_name: str = typer.Option(..., "--name", "-n", help="Name of the memory to delete")
):
    """Delete a memory instance"""
    chat_memory = ChatMemory()
    memories = chat_memory.get_memory_list()
    
    if memory_name not in memories:
        console.print(f"[red]Error: Memory '{memory_name}' does not exist.[/red]")
        return
    
    # 不允许删除当前正在使用的内存
    if memory_name == chat_memory.config.current_memory_name:
        console.print(f"[red]Error: Cannot delete current memory '{memory_name}'. Switch to another memory first.[/red]")
        return
    
    import os
    memory_path = os.path.join(chat_memory.base_path, f"{memory_name}_memory.json")
    
    try:
        os.remove(memory_path)
        console.print(f"[green]Deleted memory: {memory_name}[/green]")
        
        # 从字典中移除引用
        if memory_name in chat_memory.storage_dict:
            del chat_memory.storage_dict[memory_name]
    except OSError as e:
        console.print(f"[red]Error deleting memory file: {e}[/red]")

@memory_app.command()
def info(
    memory_name: str = typer.Option(None, "--name", "-n", help="Name of the memory to get info for (default: current memory)")
):
    """Get detailed information about a specific memory or current memory if not specified"""
    chat_memory = ChatMemory()
    
    # 如果未指定内存名称，则使用当前内存
    if memory_name is None:
        memory_name = chat_memory.config.current_memory_name
        console.print(f"[bold blue]Getting info for current memory: {memory_name}[/bold blue]")
    
    memories = chat_memory.get_memory_list()
    
    if memory_name not in memories:
        console.print(f"[red]Error: Memory '{memory_name}' does not exist.[/red]")
        return
    
    temp_storage = chat_memory._get_or_create_memory(memory_name)
    data = temp_storage.load()
    messages = data.get("messages", [])
    
    console.print(f"[bold blue]Information for memory: {memory_name}[/bold blue]")
    console.print(f"Message count: {len(messages)}")
    
    description = chat_memory.get_memory_description(memory_name)
    if description:
        console.print(f"Description: {description}")
    
    current_memory = chat_memory.config.current_memory_name
    console.print(f"Is current memory: {'Yes' if memory_name == current_memory else 'No'}")

@memory_app.command()
def update(
    memory_name: str = typer.Option(None, "--name", "-n", help="Name of the memory to update description for (default: current memory)"),
    description: str = typer.Option(..., "--desc", "-d", help="New description for the memory")
):
    """Update the description of a memory instance"""
    chat_memory = ChatMemory()
    
    # 如果未指定内存名称，则使用当前内存
    if memory_name is None:
        memory_name = chat_memory.config.current_memory_name
        console.print(f"[bold blue]Updating description for current memory: {memory_name}[/bold blue]")
    
    memories = chat_memory.get_memory_list()
    
    if memory_name not in memories:
        console.print(f"[red]Error: Memory '{memory_name}' does not exist.[/red]")
        return
    
    chat_memory.set_memory_description(memory_name, description)
    console.print(f"[green]Updated description for memory '{memory_name}': {description}[/green]")

@memory_app.command()
def read(
    memory_name: str = typer.Option(None, "--read", "-r", help="Read the memory history")
):
    """Read the memory history"""
    chat_memory = ChatMemory()
    memory_name_to_use = memory_name
    if memory_name_to_use is None:
        memory_name_to_use = chat_memory.config.current_memory_name
    
    console.print(f"[bold blue]Reading memory: {memory_name_to_use}[/bold blue]")
    
    memories = chat_memory.get_memory_list()
    if memory_name_to_use not in memories:
        console.print(f"[red]Error: Memory '{memory_name_to_use}' does not exist.[/red]")
        return

    temp_storage = chat_memory._get_or_create_memory(memory_name_to_use)
    data = temp_storage.load()
    messages = data.get("messages", [])
    
    if messages:
        console.print(f"[bold blue]Memory '{memory_name_to_use}' contains {len(messages)} messages:[/bold blue]")
        for i, msg in enumerate(messages, 1):
            role = msg.get('role', 'unknown')
            content = msg.get('content', '')
            timestamp = msg.get('timestamp', '')
            console.print(f"{i}. [{role}] {content} {f'({timestamp})' if timestamp else ''}")
    else:
        console.print(f"[yellow]Memory '{memory_name_to_use}' is empty.[/yellow]")