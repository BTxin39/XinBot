from dataclasses import dataclass
import os
from dotenv import load_dotenv

load_dotenv()

class RuntimeConfig:
    MODEL_NAME: str  = os.getenv("deepseek_model_name")
    TEMPERATURE: float = 0.7
    MAX_MEMORY_MESSAGES: int = 20