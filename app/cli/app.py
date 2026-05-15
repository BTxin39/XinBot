import typer

from app.cli.chat import chat_app

app = typer.Typer()

app.add_typer(chat_app,name="chat")

if __name__ == "__main__":
    app()