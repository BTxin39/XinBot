from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class ToolParameter:
    name: str
    type: str
    description: str
    required: bool = True
    enum: list[str] | None = None


class BaseTool(ABC):
    name: str
    description: str
    parameters: list[ToolParameter] = []

    def to_openai_schema(self) -> dict:
        properties: dict = {}
        required: list[str] = []
        for param in self.parameters:
            prop: dict = {"type": param.type, "description": param.description}
            if param.enum:
                prop["enum"] = param.enum
            properties[param.name] = prop
            if param.required:
                required.append(param.name)

        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                },
            },
        }

    @abstractmethod
    def execute(self, **kwargs) -> str:
        pass