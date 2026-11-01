from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "VERIQO API"
    postgres_dsn: str = "postgresql+asyncpg://veriqo:veriqo@localhost:5432/veriqo"
    mongo_uri: str = "mongodb://localhost:27017"
    mongo_db: str = "veriqo"
    intelligence_url: str = "http://localhost:8001"
    jwt_secret: str = "change-me"
    jwt_expire_minutes: int = 60 * 24
    # Used for per-day / per-hour grouping in the Year in Code analytics.
    display_timezone: str = "Asia/Kolkata"
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]


@lru_cache
def get_settings() -> Settings:
    return Settings()
