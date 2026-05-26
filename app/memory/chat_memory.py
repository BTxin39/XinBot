from app.memory.base import BaseMemory
from app.config.runtime import RuntimeConfig
from app.storage.json_storage import JsonStorage
import os

class ChatMemory(BaseMemory):
    def __init__(self, config: RuntimeConfig | None = None):
        self.config = config or RuntimeConfig.load()
        self.base_path = "data/memory_json"
        self.storage_dict: dict[str, JsonStorage] = {}   #[memory_name, json]
        
        os.makedirs(self.base_path, exist_ok=True)
        
        self._load_all_memory()
        
        self.storage = self._get_or_create_memory(self.config.current_memory_name)
        self.messages = self._load_messages(self.storage)

    def add_message(self, role, content):
        self.messages.append(
            {
                "role": role,
                "content": content,
            }
        )
        self._trim_messages()
        self._save_current_memory()
    
    def _trim_messages(self):
        self.messages = self.messages[
            -self.config.max_memory_messages:
        ]
    def get_message(self):
        return self.messages
    
    def clear(self):
        # 保留描述信息，只清空消息
        data = self._load_memory_data(self.storage)
        description = data.get("description", "")
        self.messages.clear()
        # 保存空消息列表但保留描述
        self.storage.save({
            "messages": [],
            "description": description
        })

    def _load_all_memory(self):
        os.makedirs(self.base_path, exist_ok=True)
        all_items = os.listdir(self.base_path)
        for file in all_items:
            if file.endswith("_memory.json"):
                memory_name = file.replace("_memory.json", "")
                self._load_memory(memory_name)

    def _load_memory(self, memory_name):
        memory_path = os.path.join(self.base_path, f"{memory_name}_memory.json")
        storage = JsonStorage(memory_path)
        self.storage_dict[memory_name] = storage

    def _get_or_create_memory(self, memory_name: str):
        if memory_name not in self.storage_dict:
            memory_path = os.path.join(self.base_path, f"{memory_name}_memory.json")
            initial_data = {"messages": [], "description": f"Memory for {memory_name}"}
            storage = JsonStorage(memory_path)
            storage.save(initial_data)
            self.storage_dict[memory_name] = storage
        
        return self.storage_dict[memory_name]

    def _load_memory_data(self, storage: JsonStorage) -> dict:
        data = storage.load()
        if isinstance(data, list):
            return {
                "messages": data,
                "description": "",
            }
        if isinstance(data, dict):
            return {
                "messages": data.get("messages", []),
                "description": data.get("description", ""),
            }
        return {
            "messages": [],
            "description": "",
        }

    def _load_messages(self, storage: JsonStorage) -> list[dict]:
        return self._load_memory_data(storage)["messages"]

    def _save_current_memory(self):
        data = self._load_memory_data(self.storage)
        data["messages"] = self.messages
        self.storage.save(data)

    def get_memory_list(self):
        return list(self.storage_dict.keys())
        
    def switch_memory(self, memory_name: str):
        self.storage = self._get_or_create_memory(memory_name)
        self.current_memory_name = memory_name
        self.messages = self._load_messages(self.storage)

    def get_memory_description(self, memory_name: str):
        if memory_name in self.storage_dict:
            data = self._load_memory_data(self.storage_dict[memory_name])
            return data.get("description", "")
        return ""
        
    def set_memory_description(self, memory_name: str, description: str):
        storage = self._get_or_create_memory(memory_name)
        data = self._load_memory_data(storage)
        data["description"] = description
        storage.save(data)
