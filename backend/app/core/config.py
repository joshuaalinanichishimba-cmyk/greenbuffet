"""Application settings, loaded from the .env file in backend/.

Always run backend commands from the backend/ folder so this file is found.
"""
from functools import lru_cache

from pydantic import field_validator, model_validator
from sqlalchemy.engine import make_url

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    DATABASE_URL: str = "postgresql+psycopg://gb_dev:devpass@localhost:5432/greenbuffet_dev"
    JWT_SECRET: str = "change-me-in-env"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 480
    CORS_ORIGINS: str = "http://localhost:5173"
    ENVIRONMENT: str = "development"
    DEMO_ENABLED: bool = False
    APP_TIMEZONE: str = "Africa/Lusaka"
    BUSINESS_NAME: str = "The Green Buffet"

    @field_validator("DATABASE_URL")
    @classmethod
    def use_psycopg(cls, value: str) -> str:
        url = make_url(value)
        if url.drivername in {"postgres", "postgresql"}:
            return url.set(drivername="postgresql+psycopg").render_as_string(hide_password=False)
        return value

    @model_validator(mode="after")
    def validate_demo_database(self):
        if self.DEMO_ENABLED:
            url = make_url(self.DATABASE_URL)
            if url.get_backend_name() != "postgresql" or not (url.database or "").endswith("_demo"):
                raise ValueError("DEMO_ENABLED requires a separate PostgreSQL database ending in _demo.")
        return self

    @property
    def hosted_demo(self) -> bool:
        return self.DEMO_ENABLED and self.ENVIRONMENT == "production"

    @property
    def cors_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
