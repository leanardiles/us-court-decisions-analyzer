"""
Application configuration settings.

This file manages environment variables and application settings.
"""

from pydantic_settings import BaseSettings
from pathlib import Path

ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.

    Create a .env file in backend/ folder.
    """

    SECRET_KEY: str = "your-secret-key-change-this-in-production-min-32-chars"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    GROQ_API_KEY: str = ""

    # Capstone I local app
    DATABASE_URL: str = "sqlite:///./database.db"

    # Shared Capstone II store (Supabase)
    SUPABASE_URL: str = ""
    SUPABASE_ANON_KEY: str = ""
    SUPABASE_KEY: str = ""  # alias for the publishable/anon key
    SUPABASE_SERVICE_ROLE_KEY: str = ""
    SUPABASE_DB_URL: str = ""
    SUPABASE_DB_PASSWORD: str = ""

    APP_NAME: str = "Court Opinions Analyzer"
    DEBUG: bool = True

    class Config:
        env_file = str(ENV_FILE)
        extra = "ignore"
        case_sensitive = True


settings = Settings()
