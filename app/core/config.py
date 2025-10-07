from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic import computed_field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application configuration loaded from environment variables."""

    data_dir: Path = Field(default=Path("var"), description="Root directory for application data")
    database_url: str = Field(
        default="sqlite:///var/app.db",
        description="SQLAlchemy database URL",
    )

    class Config:
        env_prefix = "APP_"
        env_file = ".env"

    @computed_field
    @property
    def content_dir(self) -> Path:
        return self.data_dir / "content"

    @computed_field
    @property
    def log_dir(self) -> Path:
        return self.data_dir / "logs"


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.content_dir.mkdir(parents=True, exist_ok=True)
    settings.log_dir.mkdir(parents=True, exist_ok=True)
    return settings

