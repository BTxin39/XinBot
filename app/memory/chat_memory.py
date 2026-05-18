from app.memory.base import BaseMemory
from app.config.runtime import RuntimeConfig
from app.storage.json_storage import JsonStorage

class ChatMemory(BaseMemory):
    def __init__(self, config: RuntimeConfig | None = None):
        self.config = config or RuntimeConfig.load()
        self.storage = JsonStorage(
            file_path="data/chat_memory.json"
        )
        self.messages = self.storage.load()

    def add_message(self, role, content):
        self.messages.append(
            {
                "role": role,
                "content": content,
            }
        )
        self._trim_messages()
        self.storage.save(self.messages)
    
    def _trim_messages(self):
        self.messages = self.messages[
            -self.config.MAX_MEMORY_MESSAGES:
        ]
    def get_message(self):
        return self.messages
    
    def clear(self):
        self.messages.clear()
        self.storage.save(self.messages)
