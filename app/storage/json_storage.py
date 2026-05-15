import json
from pathlib import Path
from app.storage.base import BaseStorage

class JsonStorage(BaseStorage):
    def __init__(self, file_path):
        self.file_path = Path(file_path)

    def save(self, data):
        with open(self.file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def load(self):
        if not self.file_path.exists():
            return []

        with open(
            self.file_path,
            "r",
            encoding="utf-8",
        ) as f:
            return json.load(f)