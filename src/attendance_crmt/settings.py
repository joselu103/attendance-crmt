"""Runtime configuration loaded from environment variables and a local ``.env`` file."""

from functools import cache
from pathlib import Path
from typing import Annotated, Literal
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
)
from pydantic_settings import BaseSettings, SettingsConfigDict

ATTENDANCE_DB_URL_ENV = "ATTENDANCE_DATABASE_URL"
AUDIT_DB_PATH_ENV = "ATTENDANCE_AUDIT_DATABASE_PATH"
ENTRA_TENANT_ID_ENV = "ATTENDANCE_ENTRA_TENANT_ID"
ENTRA_AUDIENCE_ENV = "ATTENDANCE_ENTRA_AUDIENCE"
ENTRA_ALLOWED_CLIENT_IDS_ENV = "ATTENDANCE_ENTRA_ALLOWED_CLIENT_IDS"
ENTRA_REQUIRED_SCOPE_ENV = "ATTENDANCE_ENTRA_REQUIRED_SCOPE"
ENTRA_ADMIN_ROLE_ENV = "ATTENDANCE_ENTRA_ADMIN_ROLE"
ENTRA_EMAIL_ALIASES_ENV = "ATTENDANCE_ENTRA_EMAIL_ALIASES"

NonBlankStr = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class EntraAuthenticationSettings(BaseModel):
    """Immutable settings required to validate delegated REST credentials."""

    model_config = ConfigDict(frozen=True)

    tenant_id: UUID
    audience: NonBlankStr
    allowed_client_ids: frozenset[UUID]
    required_scope: NonBlankStr
    admin_role: NonBlankStr

    @property
    def issuer(self) -> str:
        """Return the standard public-cloud Entra issuer for this tenant."""
        return f"https://login.microsoftonline.com/{self.tenant_id}/v2.0"

    @property
    def openid_configuration_url(self) -> str:
        """Return the standard public-cloud discovery document for this tenant."""
        return f"{self.issuer}/.well-known/openid-configuration"


class Settings(BaseSettings):
    """Immutable application configuration loaded once per process."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        frozen=True,
    )

    environment: Literal["development", "staging", "production"] = "development"
    attendance_db_url: str = Field(validation_alias=ATTENDANCE_DB_URL_ENV)
    audit_db_path: Path = Field(
        default=Path("data/audit.sqlite3"),
        validation_alias=AUDIT_DB_PATH_ENV,
    )
    entra_tenant_id: UUID = Field(validation_alias=ENTRA_TENANT_ID_ENV)
    entra_audience: NonBlankStr = Field(validation_alias=ENTRA_AUDIENCE_ENV)
    entra_allowed_client_ids: frozenset[UUID] = Field(
        validation_alias=ENTRA_ALLOWED_CLIENT_IDS_ENV
    )
    entra_required_scope: NonBlankStr = Field(
        default="attendance.access",
        validation_alias=ENTRA_REQUIRED_SCOPE_ENV,
    )
    entra_admin_role: NonBlankStr = Field(
        default="attendance.admin",
        validation_alias=ENTRA_ADMIN_ROLE_ENV,
    )
    entra_email_aliases: dict[str, str] = Field(
        default_factory=dict,
        validation_alias=ENTRA_EMAIL_ALIASES_ENV,
    )

    @field_validator("entra_allowed_client_ids")
    @classmethod
    def require_allowed_client(cls, value: frozenset[UUID]) -> frozenset[UUID]:
        """Require at least one explicitly approved REST client application."""
        if not value:
            raise ValueError("at least one allowed client ID is required")
        return value

    @field_validator("entra_email_aliases")
    @classmethod
    def normalize_entra_email_aliases(cls, value: dict[str, str]) -> dict[str, str]:
        """Normalize explicit, operator-configured Entra-to-email aliases."""
        aliases: dict[str, str] = {}
        for source, target in value.items():
            normalized_source = source.strip().lower()
            normalized_target = target.strip().lower()
            if not normalized_source or not normalized_target:
                raise ValueError("Entra email aliases must not contain blank values")
            if (
                normalized_source in aliases
                and aliases[normalized_source] != normalized_target
            ):
                raise ValueError(
                    "Entra email aliases must not conflict after normalization"
                )
            aliases[normalized_source] = normalized_target
        return aliases

    @property
    def entra_authentication(self) -> EntraAuthenticationSettings:
        """Return the cohesive token-validation settings value object."""
        return EntraAuthenticationSettings(
            tenant_id=self.entra_tenant_id,
            audience=self.entra_audience,
            allowed_client_ids=self.entra_allowed_client_ids,
            required_scope=self.entra_required_scope,
            admin_role=self.entra_admin_role,
        )


@cache
def get_settings() -> Settings:
    """Load and validate the process-wide application configuration once."""
    return Settings()
