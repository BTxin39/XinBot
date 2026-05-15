from dotenv import load_dotenv
from pathlib import Path
import os

load_dotenv()

class Settings:
    BASE_DIR = Path(__file__).resolve().parent.parent

    OPENAI_API_KEY: str | None = (
        os.getenv("OPENAI_API_KEY")
        or os.getenv("deepseek_api_key")
    )
    OPENAI_BASE_URL: str | None = (
        os.getenv("OPENAI_BASE_URL")
        or os.getenv("BASE_URL")
        or os.getenv("deepseek_base_url")
    )
    BASE_URL: str | None = (
        os.getenv("deepseek_base_url")
    )
