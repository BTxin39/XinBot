from rich.console import Console

from app.events.events import EmotionChangedEvent

console = Console()

def on_emotion_changed(
        event: EmotionChangedEvent,
):
    console.print(f"""
[yellow]
Emotion changed:
{event.old_emotion}
→
{event.new_emotion}
[/yellow]
"""
    )