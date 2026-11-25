"""Application settings, loaded from the .env file in backend/.

The file is found by its full path, not "whatever folder we were started
from", so the Windows scheduled task, a terminal and the tests all read the
same file. A DATABASE_URL set as a Windows environment variable still takes
priority over the file; run_server.py logs a warning when that happens.
"""
from functools import lru_cache
from pathlib import Path

ENV_FILE = Path(__file__).resolve().parents[2] / ".env"

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(ENV_FILE), env_file_encoding="utf-8", extra="ignore")

    DATABASE_URL: str = "postgresql+psycopg://gb_dev:devpass@localhost:5432/greenbuffet_dev"
    JWT_SECRET: str = "change-me-in-env"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 480
    CORS_ORIGINS: str = "http://localhost:5173"
    ENVIRONMENT: str = "development"
    APP_TIMEZONE: str = "Africa/Lusaka"
    BUSINESS_NAME: str = "The Green Buffet"

    @field_validator("DATABASE_URL")
    @classmethod
    def _driver(cls, value: str) -> str:
        # Hosts such as Render hand out "postgres://..." or "postgresql://...";
        # the system talks to PostgreSQL through psycopg 3.
        for plain in ("postgres://", "postgresql://"):
            if value.startswith(plain):
                return "postgresql+psycopg://" + value[len(plain):]
        return value

    @property
    def cors_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
