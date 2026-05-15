from app.memory.base import BaseMemory
from app.config.runtime import RuntimeConfig
from app.storage.json_storage import JsonStorage

class ChatMemory(BaseMemory):
    def __init__(self):
        self.config = RuntimeConfig()
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
        system_messages = self.messages[0]
        recent_messages = self.messages[-self.config.MAX_MEMORY_MESSAGES:]
        self.messages = [
            system_messages,
            *recent_messages
        ]
    def get_message(self):
        return self.messages
    
    def clear(self):
        self.messages.clear()
        self.storage.save(self.messages)