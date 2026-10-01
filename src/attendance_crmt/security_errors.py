"""Stable, safe security error contracts for REST operations."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, model_validator

AUTHENTICATION_REQUIRED_MESSAGE = "Please sign in to use Attendance."
TOKEN_INVALID_MESSAGE = "Your sign-in could not be verified. Please try again."
IDENTITY_UNMAPPED_MESSAGE = (
    "Your Teams account is not linked to an active attendance employee. "
    "Contact an administrator."
)
IDENTITY_AMBIGUOUS_MESSAGE = (
    "Your Teams account cannot be linked safely. Contact an administrator."
)
CORRELATION_ID_INVALID_MESSAGE = "The request correlation ID is missing or invalid."
INVALID_ARGUMENT_MESSAGE = (
    "Check the attendance date range and pagination values and try again."
)
FORBIDDEN_MESSAGE = "You do not have permission to do that."
BACKEND_UNAVAILABLE_MESSAGE = (
    "Attendance is temporarily unavailable. Please try again shortly."
)
INTERNAL_ERROR_MESSAGE = "Attendance could not complete that request."
NOT_FOUND_MESSAGE = "The requested attendance resource was not found."

SecurityErrorCode = Literal[
    "AUTHENTICATION_REQUIRED",
    "TOKEN_INVALID",
    "CORRELATION_ID_INVALID",
    "INVALID_ARGUMENT",
    "IDENTITY_UNMAPPED",
    "IDENTITY_AMBIGUOUS",
    "FORBIDDEN",
    "BACKEND_UNAVAILABLE",
    "INTERNAL_ERROR",
    "NOT_FOUND",
]

SECURITY_ERROR_MESSAGES: dict[SecurityErrorCode, str] = {
    "AUTHENTICATION_REQUIRED": AUTHENTICATION_REQUIRED_MESSAGE,
    "TOKEN_INVALID": TOKEN_INVALID_MESSAGE,
    "CORRELATION_ID_INVALID": CORRELATION_ID_INVALID_MESSAGE,
    "INVALID_ARGUMENT": INVALID_ARGUMENT_MESSAGE,
    "IDENTITY_UNMAPPED": IDENTITY_UNMAPPED_MESSAGE,
    "IDENTITY_AMBIGUOUS": IDENTITY_AMBIGUOUS_MESSAGE,
    "FORBIDDEN": FORBIDDEN_MESSAGE,
    "BACKEND_UNAVAILABLE": BACKEND_UNAVAILABLE_MESSAGE,
    "INTERNAL_ERROR": INTERNAL_ERROR_MESSAGE,
    "NOT_FOUND": NOT_FOUND_MESSAGE,
}

SECURITY_ERROR_STATUS_CODES: dict[SecurityErrorCode, int] = {
    "AUTHENTICATION_REQUIRED": 401,
    "TOKEN_INVALID": 401,
    "CORRELATION_ID_INVALID": 400,
    "INVALID_ARGUMENT": 400,
    "IDENTITY_UNMAPPED": 403,
    "IDENTITY_AMBIGUOUS": 403,
    "FORBIDDEN": 403,
    "BACKEND_UNAVAILABLE": 503,
    "INTERNAL_ERROR": 500,
    "NOT_FOUND": 404,
}


class SecurityFailure(Exception):
    """Typed internal failure with a fixed public REST representation."""

    def __init__(
        self,
        *,
        code: SecurityErrorCode,
        actor_id: str | None = None,
    ) -> None:
        self.code: SecurityErrorCode = code
        self.actor_id = actor_id
        super().__init__(code)

    @property
    def response(self) -> SecurityErrorResponse:
        """Return the canonical public response without internal diagnostics."""
        return SecurityErrorResponse(
            code=self.code,
            message=SECURITY_ERROR_MESSAGES[self.code],
        )


class SecurityErrorResponse(BaseModel):
    """Machine-readable security failure with no sensitive diagnostics."""

    model_config = ConfigDict(frozen=True)

    code: SecurityErrorCode
    message: str

    @model_validator(mode="after")
    def require_safe_message_for_code(self) -> SecurityErrorResponse:
        """Prevent arbitrary diagnostics from crossing the public boundary."""
        if self.message != SECURITY_ERROR_MESSAGES[self.code]:
            raise ValueError("security error code requires its configured safe message")
        return self
