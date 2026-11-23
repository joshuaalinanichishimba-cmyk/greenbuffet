"""Application settings, loaded from the .env file in backend/.

Always run backend commands from the backend/ folder so this file is found.
"""
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    DATABASE_URL: str = "postgresql+psycopg://gb_dev:devpass@localhost:5432/greenbuffet_dev"
    JWT_SECRET: str = "change-me-in-env"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 480
    CORS_ORIGINS: str = "http://localhost:5173"
    ENVIRONMENT: str = "development"
    POS_FRONTEND_DIR: Path | None = None
    APP_TIMEZONE: str = "Africa/Lusaka"
    BUSINESS_NAME: str = "The Green Buffet"

    @property
    def cors_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
