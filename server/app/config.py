"""Single place that reads environment configuration. Nothing else reads os.environ."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://postgres:dev@db:5432/nirantharseva"

    jwt_secret: str = "dev-secret-change-for-anything-real"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 480

    # See docs/decisions/ADR-001.md — real|simulated
    clock_mode: str = "real"
    sim_start: str | None = None

    run_id: str | None = None
    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    return Settings()
