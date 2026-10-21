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
    allowed_origins: str = Field(
        default="http://localhost:3000,http://127.0.0.1:3000", validation_alias="ALLOWED_ORIGINS"
    )
    secure_cookies: bool = Field(default=False, validation_alias="SECURE_COOKIES")
    watch_interval_seconds: int = Field(default=21600, ge=60, validation_alias="WATCH_INTERVAL_SECONDS")
    max_file_bytes: int = Field(default=1048576, validation_alias="MAX_FILE_BYTES")
    registration_enabled: bool = Field(default=True, validation_alias="REGISTRATION_ENABLED")
    max_projects_per_user: int = Field(default=10, ge=1, le=100, validation_alias="MAX_PROJECTS_PER_USER")
    max_active_jobs_per_user: int = Field(default=3, ge=1, le=20, validation_alias="MAX_ACTIVE_JOBS_PER_USER")
    max_analysis_jobs_per_hour: int = Field(default=10, ge=1, le=1000, validation_alias="MAX_ANALYSIS_JOBS_PER_HOUR")
    max_owner_storage_bytes: int = Field(default=67108864, ge=1048576, validation_alias="MAX_OWNER_STORAGE_BYTES")
    max_report_bytes: int = Field(default=8388608, ge=1048576, validation_alias="MAX_REPORT_BYTES")
    max_sessions_per_user: int = Field(default=20, ge=2, le=100, validation_alias="MAX_SESSIONS_PER_USER")
    retained_scans_per_project: int = Field(default=30, ge=2, le=1000, validation_alias="RETAINED_SCANS_PER_PROJECT")
    retained_status_changes_per_project: int = Field(
        default=1000, ge=10, le=10000, validation_alias="RETAINED_STATUS_CHANGES_PER_PROJECT"
    )
    terminal_job_retention_days: int = Field(default=30, ge=1, le=365, validation_alias="TERMINAL_JOB_RETENTION_DAYS")
    notification_retention_days: int = Field(default=90, ge=1, le=365, validation_alias="NOTIFICATION_RETENTION_DAYS")


@lru_cache
def get_settings() -> Settings:
    return Settings()
