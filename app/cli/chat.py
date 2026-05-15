from rich.console import Console
from app.agent.agent import Agent
from app.commands.handler import CommandHandler

console = Console()

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