from uuid import UUID

import pytest
from pydantic import ValidationError

from attendance_crmt.settings import Settings


def test_settings_build_typed_entra_mcp_authentication() -> None:
    settings = Settings(_env_file=None)

    authentication = settings.entra_mcp_authentication

    assert authentication.tenant_id == UUID("11111111-1111-1111-1111-111111111111")
    assert str(authentication.mcp_base_url) == "http://localhost:8000/"
    assert authentication.audience == "api://attendance-crmt-test"
    assert authentication.allowed_client_ids == frozenset(
        {UUID("22222222-2222-2222-2222-222222222222")}
    )
    assert authentication.required_scope == "attendance.access"
    assert authentication.clock_skew_seconds == 60
    assert authentication.admin_role == "attendance.admin"

    with pytest.raises(ValidationError, match="frozen"):
        authentication.audience = "api://other"  # type: ignore[misc]


def test_settings_reject_empty_allowed_client_ids(monkeypatch) -> None:
    monkeypatch.setenv("ATTENDANCE_ENTRA_ALLOWED_CLIENT_IDS", "[]")

    with pytest.raises(ValidationError, match="allowed client"):
        Settings(_env_file=None)


def test_settings_normalize_explicit_entra_email_aliases(monkeypatch) -> None:
    monkeypatch.setenv(
        "ATTENDANCE_ENTRA_EMAIL_ALIASES",
        '{" JoseLuisCambil@AttendanceCRMTDevelopment.onmicrosoft.com ": '
        '" JoseLuisCC103@gmail.com "}',
    )

    settings = Settings(_env_file=None)

    assert settings.entra_email_aliases == {
        "joseluiscambil@attendancecrmtdevelopment.onmicrosoft.com": (
            "joseluiscc103@gmail.com"
        )
    }


@pytest.mark.parametrize(
    "name,value",
    [
        ("ATTENDANCE_MCP_BASE_URL", "http://attendance.example.com"),
        (
            "ATTENDANCE_ENTRA_ISSUER",
            "http://login.microsoftonline.com/tenant/v2.0",
        ),
        (
            "ATTENDANCE_ENTRA_OPENID_CONFIGURATION_URL",
            "http://login.microsoftonline.com/tenant/openid-configuration",
        ),
    ],
)
def test_production_settings_require_https_authentication_urls(
    monkeypatch, name: str, value: str
) -> None:
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv(name, value)

    with pytest.raises(ValidationError, match="HTTPS"):
        Settings(_env_file=None)


def test_settings_reject_mismatched_openid_and_issuer_authorities(
    monkeypatch,
) -> None:
    monkeypatch.setenv(
        "ATTENDANCE_ENTRA_OPENID_CONFIGURATION_URL",
        "https://example.com/.well-known/openid-configuration",
    )

    with pytest.raises(ValidationError, match="same authority"):
        Settings(_env_file=None)
