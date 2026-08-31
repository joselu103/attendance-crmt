import pytest
from fastmcp.exceptions import ToolError
from pydantic import ValidationError

from attendance_crmt.security_errors import (
    FORBIDDEN_MESSAGE,
    INVALID_ARGUMENT_MESSAGE,
    TOKEN_INVALID_MESSAGE,
    SecurityErrorResponse,
    SecurityFailure,
)


def test_security_failure_derives_the_canonical_safe_response() -> None:
    failure = SecurityFailure(code="FORBIDDEN")

    assert failure.code == "FORBIDDEN"
    assert failure.actor_id is None
    assert failure.response == SecurityErrorResponse(
        code="FORBIDDEN",
        message=FORBIDDEN_MESSAGE,
    )
    assert isinstance(failure.as_tool_error(), ToolError)


def test_security_failure_keeps_actor_context_out_of_public_response() -> None:
    failure = SecurityFailure(
        code="IDENTITY_UNMAPPED",
        actor_id="tenant-id:object-id",
    )

    assert failure.actor_id == "tenant-id:object-id"
    assert "tenant-id:object-id" not in failure.response.model_dump_json()


def test_invalid_argument_failure_uses_canonical_safe_payload() -> None:
    failure = SecurityFailure(code="INVALID_ARGUMENT")

    assert failure.response.model_dump(mode="json") == {
        "code": "INVALID_ARGUMENT",
        "message": INVALID_ARGUMENT_MESSAGE,
    }


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


@pytest.mark.parametrize(
    ("code", "message"),
    [
        (
            "CORRELATION_ID_INVALID",
            "The request correlation ID is missing or invalid.",
        ),
        ("FORBIDDEN", "You do not have permission to do that."),
        (
            "BACKEND_UNAVAILABLE",
            "Attendance is temporarily unavailable. Please try again shortly.",
        ),
        ("INTERNAL_ERROR", "Attendance could not complete that request."),
    ],
)
def test_security_error_response_serializes_new_stable_safe_messages(
    code: str, message: str
) -> None:
    response = SecurityErrorResponse(code=code, message=message)  # type: ignore[arg-type]

    assert response.model_dump(mode="json") == {"code": code, "message": message}


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
