import os
from functools import lru_cache

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration.

    Environment variables override these defaults, and a local `.env` file is
    read when present. Tests set the environment before the process imports
    the application, so they never touch the developer's database.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Bulk Certificate Generator"
    database_url: str = "sqlite:///./data/certificates.db"
    storage_dir: str = "./storage/certificates"
    public_base_url: str = "http://127.0.0.1:8000"
    max_recipients_per_job: int = 500
    worker_enabled: bool = True
    worker_poll_interval_seconds: float = 0.5
    api_key: str | None = None
    cors_origins: str = "*"

    @field_validator("api_key", mode="before")
    @classmethod
    def blank_api_key_disables_auth(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("public_base_url", mode="before")
    @classmethod
    def use_vercel_host(cls, value: object) -> object:
        if value in (None, "", "http://127.0.0.1:8000"):
            host = os.environ.get("VERCEL_PROJECT_PRODUCTION_URL") or os.environ.get("VERCEL_URL")
            if host:
                host = str(host).removeprefix("https://").removeprefix("http://").strip("/")
                return f"https://{host}"
        return value

    @field_validator("public_base_url")
    @classmethod
    def normalize_base_url(cls, value: str) -> str:
        normalized = value.rstrip("/")
        if not normalized.startswith(("http://", "https://")):
            raise ValueError("PUBLIC_BASE_URL must start with http:// or https://")
        return normalized

    @model_validator(mode="after")
    def vercel_uses_tmp(self) -> "Settings":
        if os.environ.get("VERCEL") != "1":
            return self
        if self.database_url == "sqlite:///./data/certificates.db":
            self.database_url = "sqlite:////tmp/certificates.db"
        if self.storage_dir == "./storage/certificates":
            self.storage_dir = "/tmp/certificates"
        return self

    @field_validator("max_recipients_per_job")
    @classmethod
    def recipient_limit_is_positive(cls, value: int) -> int:
        if value < 1:
            raise ValueError("MAX_RECIPIENTS_PER_JOB must be at least 1")
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
