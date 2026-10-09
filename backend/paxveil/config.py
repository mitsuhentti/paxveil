from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=False)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(Path(__file__).resolve().parents[2] / ".env"), extra="ignore")
    database_url: str = Field(default="sqlite:///./runtime/paxveil.sqlite", validation_alias="DATABASE_URL")
    bot_key: str = Field(default="", validation_alias="PAXVEIL_BOT_KEY")
    telegram_token: str = Field(default="", validation_alias="TELEGRAM_BOT_TOKEN")
    api_url: str = Field(default="http://127.0.0.1:8000", validation_alias="PAXVEIL_API_URL")
    web_url: str = Field(default="http://localhost:3000", validation_alias="PAXVEIL_WEB_URL")
    allowed_origins: str = Field(default="http://localhost:3000,http://127.0.0.1:3000", validation_alias="ALLOWED_ORIGINS")
    secure_cookies: bool = Field(default=False, validation_alias="SECURE_COOKIES")
    watch_interval_seconds: int = Field(default=21600, ge=60, validation_alias="WATCH_INTERVAL_SECONDS")
    max_file_bytes: int = Field(default=1048576, validation_alias="MAX_FILE_BYTES")
    registration_enabled: bool = Field(default=True, validation_alias="REGISTRATION_ENABLED")


@lru_cache
def get_settings() -> Settings:
    return Settings()
