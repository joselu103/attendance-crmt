from uuid import UUID

import pytest
from pydantic import ValidationError

from attendance_crmt.settings import Settings


def test_settings_build_typed_entra_authentication() -> None:
    settings = Settings(_env_file=None)

    authentication = settings.entra_authentication

    assert authentication.tenant_id == UUID("11111111-1111-1111-1111-111111111111")
    assert authentication.issuer == (
        "https://login.microsoftonline.com/11111111-1111-1111-1111-111111111111/v2.0"
    )
    assert authentication.openid_configuration_url == (
        "https://login.microsoftonline.com/11111111-1111-1111-1111-111111111111/"
        "v2.0/.well-known/openid-configuration"
    )
    assert authentication.audience == "api://attendance-crmt-test"
    assert authentication.allowed_client_ids == frozenset(
        {UUID("22222222-2222-2222-2222-222222222222")}
    )
    assert authentication.required_scope == "attendance.access"
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
