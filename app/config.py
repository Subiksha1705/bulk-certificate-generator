from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration loaded from environment variables or .env file."""

    DATABASE_URL: str = "sqlite:///./certificates.db"
    STORAGE_DIR: str = "./storage"
    PUBLIC_BASE_URL: str = "http://localhost:8000"
    MAX_RECIPIENTS_PER_JOB: int = 1000
    RECOVER_ON_STARTUP: bool = True
    ENABLE_DEMO_FAILURES: bool = False
    SIMULATED_DELAY_MS: int = 0
    ENVIRONMENT: str = "dev"
    LOG_LEVEL: str = "INFO"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    """Cached settings instance."""
    return Settings()
