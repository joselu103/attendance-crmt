"""Requester identity abstractions independent of server composition."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol
from uuid import UUID

from fastmcp.exceptions import ToolError
from fastmcp.server.auth import AccessToken
from fastmcp.server.dependencies import get_access_token
from sqlalchemy import func, select
from sqlalchemy.exc import MultipleResultsFound, NoResultFound
from sqlalchemy.orm import Session, sessionmaker

from attendance_crmt.models import Employee
from attendance_crmt.security_errors import (
    IDENTITY_AMBIGUOUS_MESSAGE,
    IDENTITY_UNMAPPED_MESSAGE,
    TOKEN_INVALID_MESSAGE,
    SecurityErrorCode,
    SecurityErrorResponse,
)


@dataclass(frozen=True)
class Requester:
    """The server-derived identity acting through an MCP request."""

    actor_id: str
    roles: frozenset[str]
    employee_id: int | None = None


class RequesterResolver(Protocol):
    """Resolve the requester for the current transport context."""

    def resolve(self, context: Any) -> Requester:
        """Return the requester identity for one tool invocation."""
        ...


class EmailIdentityUnmappedError(LookupError):
    """Raised when no active employee matches a validated Teams email."""


class EmailIdentityAmbiguousError(LookupError):
    """Raised when multiple active employees match a validated Teams email."""


@dataclass(frozen=True)
class StaticRequesterResolver:
    """Development-only resolver until transport authentication is available."""

    requester: Requester

    def resolve(self, context: Any) -> Requester:
        """Return the configured MVP requester identity."""
        return self.requester


def create_mvp_requester_resolver(
    employee_id: int | None = None,
) -> StaticRequesterResolver:
    """Create the fixed read-only MVP administrator requester."""
    return StaticRequesterResolver(
        Requester(
            actor_id="mvp-admin",
            roles=frozenset({"admin"}),
            employee_id=employee_id,
        )
    )


def resolve_active_employee_id_for_email(
    *, session_factory: sessionmaker[Session], email: str
) -> int:
    """Resolve one active employee from a validated Teams sign-in email."""
    normalized_email = email.strip().lower()
    statement = select(Employee.izvajalec_id).where(
        Employee.active == 1,
        func.lower(func.ltrim(func.rtrim(Employee.email))) == normalized_email,
    )
    with session_factory() as session:
        try:
            return session.scalars(statement).one()
        except NoResultFound as error:
            raise EmailIdentityUnmappedError from error
        except MultipleResultsFound as error:
            raise EmailIdentityAmbiguousError from error


@dataclass(frozen=True)
class AuthenticatedTokenRequesterResolver:
    """Derive one requester exclusively from FastMCP's validated access token."""

    session_factory: sessionmaker[Session]
    admin_role: str
    access_token_provider: Callable[[], AccessToken | None] = get_access_token

    def resolve(self, context: Any) -> Requester:
        """Map validated delegated-user claims to one active employee."""
        access_token = self.access_token_provider()
        if access_token is None:
            raise self._token_invalid_error()

        claims = access_token.claims
        try:
            tenant_id = UUID(str(claims["tid"]))
            object_id = UUID(str(claims["oid"]))
            raw_email = claims["preferred_username"]
        except KeyError, TypeError, ValueError:
            raise self._token_invalid_error() from None
        if not isinstance(raw_email, str):
            raise self._token_invalid_error()
        email = raw_email.strip().lower()
        if not email:
            raise self._token_invalid_error()

        try:
            employee_id = resolve_active_employee_id_for_email(
                session_factory=self.session_factory,
                email=email,
            )
        except EmailIdentityUnmappedError:
            raise self._identity_error(
                code="IDENTITY_UNMAPPED",
                message=IDENTITY_UNMAPPED_MESSAGE,
            ) from None
        except EmailIdentityAmbiguousError:
            raise self._identity_error(
                code="IDENTITY_AMBIGUOUS",
                message=IDENTITY_AMBIGUOUS_MESSAGE,
            ) from None

        roles = {"employee"}
        if self._has_admin_role(claims.get("roles")):
            roles.add("admin")
        return Requester(
            actor_id=f"{tenant_id}:{object_id}",
            roles=frozenset(roles),
            employee_id=employee_id,
        )

    def _has_admin_role(self, raw_roles: Any) -> bool:
        if not isinstance(raw_roles, (list, tuple, set, frozenset)):
            return False
        return any(role == self.admin_role for role in raw_roles)

    @staticmethod
    def _identity_error(*, code: SecurityErrorCode, message: str) -> ToolError:
        response = SecurityErrorResponse(code=code, message=message)
        return ToolError(response.model_dump_json())

    @staticmethod
    def _token_invalid_error() -> ToolError:
        response = SecurityErrorResponse(
            code="TOKEN_INVALID",
            message=TOKEN_INVALID_MESSAGE,
        )
        return ToolError(response.model_dump_json())
