import json
from dataclasses import asdict, dataclass, field
from pathlib import Path


UI_SETTINGS_PATH = Path("data/ui_settings.json")


DEFAULT_EMOTION_PICTURES = {
    "normal": "[picture_normal]",
    "happy": "[picture_happy]",
    "sad": "[picture_sad]",
    "angry": "[picture_angry]",
    "sleepy": "[picture_sleepy]",
}


@dataclass
class UISettings:
    history_display_lines: int = 6
    emotion_pictures: dict[str, str] = field(
        default_factory=lambda: DEFAULT_EMOTION_PICTURES.copy()
    )

    @classmethod
    def load(cls) -> "UISettings":
        if not UI_SETTINGS_PATH.exists():
            settings = cls()
            settings.save()
            return settings

        with open(UI_SETTINGS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)

        pictures = DEFAULT_EMOTION_PICTURES.copy()
        pictures.update(data.get("emotion_pictures", {}))

        return cls(
            history_display_lines=data.get(
                "history_display_lines",
                cls.history_display_lines,
            ),
            emotion_pictures=pictures,
        )

    def save(self) -> None:
        UI_SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(UI_SETTINGS_PATH, "w", encoding="utf-8") as f:
            json.dump(asdict(self), f, ensure_ascii=False, indent=2)

    def cli_pet_picture_for(self, emotion: str) -> str:
        return self.emotion_pictures.get(
            emotion,
            self.emotion_pictures["normal"],
        )
