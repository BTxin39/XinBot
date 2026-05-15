from dotenv import load_dotenv
from pathlib import Path
import os

load_dotenv()

class Settings:
    BASE_DIR = Path(__file__).resolve().parent.parent

    OPENAI_API_KEY: str | None = (
        os.getenv("deepseek_api_key")
    )
    BASE_URL: str = (
        os.getenv("deepseek_base_url")
    )
