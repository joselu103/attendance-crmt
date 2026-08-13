"""Runtime configuration loaded from environment variables and a local ``.env`` file."""

from functools import cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ATTENDANCE_DB_URL_ENV = "ATTENDANCE_DATABASE_URL"
AUDIT_DB_PATH_ENV = "ATTENDANCE_AUDIT_DATABASE_PATH"


class Settings(BaseSettings):
    """Immutable application configuration loaded once per process."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        frozen=True,
    )

    server_name: str = "attendance-crmt"
    server_instructions: str = "Interact with the CRMT attendance system."
    environment: Literal["development", "production"] = "development"
    attendance_db_url: str = Field(validation_alias=ATTENDANCE_DB_URL_ENV)
    audit_db_path: Path = Field(
        default=Path("data/audit.sqlite3"),
        validation_alias=AUDIT_DB_PATH_ENV,
    )


@cache
def get_settings() -> Settings:
    """Load and validate the process-wide application configuration once."""
    return Settings()
