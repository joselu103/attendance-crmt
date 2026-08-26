import pytest
from pydantic import ValidationError

from attendance_crmt.security_errors import (
    TOKEN_INVALID_MESSAGE,
    SecurityErrorResponse,
)


def test_security_error_response_serializes_stable_code_and_safe_message() -> None:
    response = SecurityErrorResponse(
        code="TOKEN_INVALID",
        message=TOKEN_INVALID_MESSAGE,
    )

    assert response.model_dump(mode="json") == {
        "code": "TOKEN_INVALID",
        "message": "Your sign-in could not be verified. Please try again.",
    }

    with pytest.raises(ValidationError, match="frozen"):
        response.code = "AUTHENTICATION_REQUIRED"  # type: ignore[misc]


def test_security_error_response_rejects_arbitrary_diagnostic_message() -> None:
    with pytest.raises(ValidationError, match="safe message"):
        SecurityErrorResponse(
            code="TOKEN_INVALID",
            message="JWT expired for person@example.com",
        )


def test_security_error_response_rejects_message_for_different_code() -> None:
    with pytest.raises(ValidationError, match="safe message"):
        SecurityErrorResponse(
            code="TOKEN_INVALID",
            message="Please sign in to use Attendance.",
        )
