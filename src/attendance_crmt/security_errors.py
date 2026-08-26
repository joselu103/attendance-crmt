"""Stable, safe security error contracts shared across transport boundaries."""

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

SecurityErrorCode = Literal[
    "AUTHENTICATION_REQUIRED",
    "TOKEN_INVALID",
    "IDENTITY_UNMAPPED",
    "IDENTITY_AMBIGUOUS",
]

SECURITY_ERROR_MESSAGES: dict[SecurityErrorCode, str] = {
    "AUTHENTICATION_REQUIRED": AUTHENTICATION_REQUIRED_MESSAGE,
    "TOKEN_INVALID": TOKEN_INVALID_MESSAGE,
    "IDENTITY_UNMAPPED": IDENTITY_UNMAPPED_MESSAGE,
    "IDENTITY_AMBIGUOUS": IDENTITY_AMBIGUOUS_MESSAGE,
}


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
