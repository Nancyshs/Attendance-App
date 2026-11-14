"""Application configuration, loaded from environment variables / .env file."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]
PROJECT_DIR = BACKEND_DIR.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        # later files win: project-level .env first, backend/.env overrides it
        env_file=(str(PROJECT_DIR / ".env"), str(BACKEND_DIR / ".env")),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Attendance & Feedback"
    environment: str = "production"  # production | development | test
    secret_key: str

    # Database (MySQL)
    database_url: str = "mysql+pymysql://attendance:change-me@127.0.0.1:3306/attendance?charset=utf8mb4"
    db_pool_size: int = 10
    db_max_overflow: int = 10
    db_pool_timeout: int = 15
    db_pool_recycle: int = 1800

    # Time / locale
    timezone: str = "Africa/Cairo"

    # Web
    public_url: str = "http://localhost:8000"
    # Set by deploy/run_server.ps1. 0 means: port 8473 while developing, 8000 on the server.
    survey_bind_port: int = 0
    survey_https: bool = False
    cors_origins: str = ""  # comma separated list, empty = same-origin only
    trust_proxy: bool = False  # honour X-Forwarded-For (set true behind IIS/Nginx)
    frontend_dist: str = str(PROJECT_DIR / "frontend" / "dist")
    media_dir: str = str(BACKEND_DIR / "data")

    # Auth
    access_token_minutes: int = 720
    trainee_token_minutes: int = 720

    # Badge PDF
    badge_font_path: str = ""

    @field_validator("secret_key")
    @classmethod
    def _secret_long_enough(cls, v: str) -> str:
        if len(v) < 32:
            raise ValueError("SECRET_KEY must be at least 32 characters long")
        return v

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.environment.lower() == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]


settings = get_settings()
