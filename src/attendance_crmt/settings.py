"""Runtime configuration loaded from environment variables and a local ``.env`` file."""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

DATABASE_URL_ENV = "ATTENDANCE_DATABASE_URL"


class Settings(BaseSettings):
    """Application settings.

    Environment variables take precedence over values in the optional local
    ``.env`` file. Do not commit the file because the database URL contains
    credentials.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = Field(validation_alias=DATABASE_URL_ENV)
