from dataclasses import dataclass

@dataclass
class ChatResponse:
    content: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int