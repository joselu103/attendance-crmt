"""Runtime configuration loaded from environment variables and a local ``.env`` file."""

from functools import cache
from pathlib import Path
from typing import Annotated, Literal
from uuid import UUID

from pydantic import (
    AnyHttpUrl,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)
from pydantic_settings import BaseSettings, SettingsConfigDict

ATTENDANCE_DB_URL_ENV = "ATTENDANCE_DATABASE_URL"
AUDIT_DB_PATH_ENV = "ATTENDANCE_AUDIT_DATABASE_PATH"
MCP_BASE_URL_ENV = "ATTENDANCE_MCP_BASE_URL"
ENTRA_TENANT_ID_ENV = "ATTENDANCE_ENTRA_TENANT_ID"
ENTRA_ISSUER_ENV = "ATTENDANCE_ENTRA_ISSUER"
ENTRA_OPENID_CONFIGURATION_URL_ENV = "ATTENDANCE_ENTRA_OPENID_CONFIGURATION_URL"
ENTRA_AUDIENCE_ENV = "ATTENDANCE_ENTRA_AUDIENCE"
ENTRA_ALLOWED_CLIENT_IDS_ENV = "ATTENDANCE_ENTRA_ALLOWED_CLIENT_IDS"
ENTRA_REQUIRED_SCOPE_ENV = "ATTENDANCE_ENTRA_REQUIRED_SCOPE"
ENTRA_CLOCK_SKEW_SECONDS_ENV = "ATTENDANCE_ENTRA_CLOCK_SKEW_SECONDS"
ENTRA_ADMIN_ROLE_ENV = "ATTENDANCE_ENTRA_ADMIN_ROLE"

NonBlankStr = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class EntraMcpAuthenticationSettings(BaseModel):
    """Immutable settings required to validate Entra tokens for the MCP API."""

    model_config = ConfigDict(frozen=True)

    mcp_base_url: AnyHttpUrl
    tenant_id: UUID
    issuer: AnyHttpUrl
    openid_configuration_url: AnyHttpUrl
    audience: NonBlankStr
    allowed_client_ids: frozenset[UUID]
    required_scope: NonBlankStr
    clock_skew_seconds: int
    admin_role: NonBlankStr


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
    mcp_base_url: AnyHttpUrl = Field(validation_alias=MCP_BASE_URL_ENV)
    entra_tenant_id: UUID = Field(validation_alias=ENTRA_TENANT_ID_ENV)
    entra_issuer: AnyHttpUrl = Field(validation_alias=ENTRA_ISSUER_ENV)
    entra_openid_configuration_url: AnyHttpUrl = Field(
        validation_alias=ENTRA_OPENID_CONFIGURATION_URL_ENV
    )
    entra_audience: NonBlankStr = Field(validation_alias=ENTRA_AUDIENCE_ENV)
    entra_allowed_client_ids: frozenset[UUID] = Field(
        validation_alias=ENTRA_ALLOWED_CLIENT_IDS_ENV
    )
    entra_required_scope: NonBlankStr = Field(
        default="attendance.access",
        validation_alias=ENTRA_REQUIRED_SCOPE_ENV,
    )
    entra_clock_skew_seconds: int = Field(
        default=60,
        ge=0,
        le=300,
        validation_alias=ENTRA_CLOCK_SKEW_SECONDS_ENV,
    )
    entra_admin_role: NonBlankStr = Field(
        default="attendance.admin",
        validation_alias=ENTRA_ADMIN_ROLE_ENV,
    )

    @field_validator("entra_allowed_client_ids")
    @classmethod
    def require_allowed_client(cls, value: frozenset[UUID]) -> frozenset[UUID]:
        """Require at least one explicitly approved MCP client application."""
        if not value:
            raise ValueError("at least one allowed client ID is required")
        return value

    @model_validator(mode="after")
    def validate_authentication_urls(self) -> Settings:
        """Keep identity metadata on one authority and require HTTPS in production."""
        if self.environment == "production":
            urls = (
                self.mcp_base_url,
                self.entra_issuer,
                self.entra_openid_configuration_url,
            )
            if any(url.scheme != "https" for url in urls):
                raise ValueError("production authentication URLs must use HTTPS")

        issuer_authority = (self.entra_issuer.host, self.entra_issuer.port)
        metadata_authority = (
            self.entra_openid_configuration_url.host,
            self.entra_openid_configuration_url.port,
        )
        if issuer_authority != metadata_authority:
            raise ValueError("issuer and OpenID metadata must use the same authority")
        return self

    @property
    def entra_mcp_authentication(self) -> EntraMcpAuthenticationSettings:
        """Return the cohesive token-validation settings value object."""
        return EntraMcpAuthenticationSettings(
            mcp_base_url=self.mcp_base_url,
            tenant_id=self.entra_tenant_id,
            issuer=self.entra_issuer,
            openid_configuration_url=self.entra_openid_configuration_url,
            audience=self.entra_audience,
            allowed_client_ids=self.entra_allowed_client_ids,
            required_scope=self.entra_required_scope,
            clock_skew_seconds=self.entra_clock_skew_seconds,
            admin_role=self.entra_admin_role,
        )


@cache
def get_settings() -> Settings:
    """Load and validate the process-wide application configuration once."""
    return Settings()
