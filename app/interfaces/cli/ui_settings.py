"""终端宠物 UI 设置（app/interfaces/cli 私有）。

原路径 `app/config/cli_ui_settings.py` 属于归属错误：该模块只服务终端宠物
（ascii 图案、历史显示行数），却躺在通用 `config/` 包中并反向导入 `app/interfaces/cli`。
见 docs/DECISIONS_V0.2.md §5.2 与 P0-2。

调用方：`app/interfaces/cli/{start,config,doctor,desktop_ui}.py`
"""

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from app.interfaces.cli.ascii_pets import Q_PETS


UI_SETTINGS_PATH = Path("data/ui_settings.json")


DEFAULT_EMOTION_PICTURES = Q_PETS.copy()


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
