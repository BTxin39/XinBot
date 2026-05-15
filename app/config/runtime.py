from dataclasses import dataclass
import os
from dotenv import load_dotenv

load_dotenv()

@dataclass
class RuntimeConfig:
    MODEL_NAME: str = (
        os.getenv("OPENAI_MODEL")
        or os.getenv("deepseek_model_name")
        or "gpt-4o-mini"
    )
    TEMPERATURE: float = 0.7
    MAX_MEMORY_MESSAGES: int = 20
    PROVIDER: str = "openai"
    
