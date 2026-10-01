"""Server-derived principal construction independent of transport composition."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import MultipleResultsFound, NoResultFound, SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from attendance_crmt.authentication import VerifiedDelegatedAccessToken
from attendance_crmt.models import Employee
from attendance_crmt.security_errors import SecurityErrorCode, SecurityFailure


@dataclass(frozen=True)
class Principal:
    """The immutable, server-derived identity authorized by Attendance CRMT."""

    actor_id: str
    roles: frozenset[str]
    employee_id: int | None = None
    client_id: str | None = None
    auth_method: str = "delegated_bearer"


Requester = Principal


class PrincipalResolver(Protocol):
    """Construct a principal from an already verified delegated access token."""

    def resolve_access_token(
        self, access_token: VerifiedDelegatedAccessToken | None
    ) -> Principal:
        """Return the server-derived principal for one verified token."""

        ...


class EmailIdentityUnmappedError(LookupError):
    """Raised when no active employee matches a validated Teams email."""


class EmailIdentityAmbiguousError(LookupError):
    """Raised when multiple active employees match a validated Teams email."""


def normalized_active_employee_email_expression():
    """Return the SQL key used for active-employee email identity matching."""
    return func.lower(func.ltrim(func.rtrim(Employee.email)))


def active_employee_with_usable_email_conditions() -> tuple[object, ...]:
    """Return the shared SQL predicates for a usable active employee email."""
    normalized_email = normalized_active_employee_email_expression()
    return (
        Employee.active == 1,
        Employee.email.is_not(None),
        normalized_email != "",
    )


def resolve_active_employee_id_for_email(
    *, session_factory: sessionmaker[Session], email: str
) -> int:
    """Resolve one active employee from a validated Teams sign-in email."""
    normalized_email = email.strip().lower()
    statement = select(Employee.izvajalec_id).where(
        Employee.active == 1,
        normalized_active_employee_email_expression() == normalized_email,
    )
    with session_factory() as session:
        try:
            return session.scalars(statement).one()
        except NoResultFound as error:
            raise EmailIdentityUnmappedError from error
        except MultipleResultsFound as error:
            raise EmailIdentityAmbiguousError from error


@dataclass(frozen=True)
class DelegatedPrincipalResolver:
    """Derive one principal from a verified delegated token."""

    session_factory: sessionmaker[Session]
    admin_role: str
    email_aliases: Mapping[str, str] = field(default_factory=dict)

    def resolve_access_token(
        self, access_token: VerifiedDelegatedAccessToken | None
    ) -> Principal:
        """Map one verified delegated-user token to one active employee."""
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
        mapped_email = self.email_aliases.get(email, email)
        actor_id = f"{tenant_id}:{object_id}"

        try:
            employee_id = resolve_active_employee_id_for_email(
                session_factory=self.session_factory,
                email=mapped_email,
            )
        except EmailIdentityUnmappedError:
            raise self._identity_error(
                code="IDENTITY_UNMAPPED",
                actor_id=actor_id,
            ) from None
        except EmailIdentityAmbiguousError:
            raise self._identity_error(
                code="IDENTITY_AMBIGUOUS",
                actor_id=actor_id,
            ) from None
        except SQLAlchemyError:
            raise self._identity_error(
                code="BACKEND_UNAVAILABLE",
                actor_id=actor_id,
            ) from None

        roles = {"employee"}
        if self._has_admin_role(claims.get("roles")):
            roles.add("admin")
        return Principal(
            actor_id=actor_id,
            roles=frozenset(roles),
            employee_id=employee_id,
            client_id=access_token.client_id,
        )

    def _has_admin_role(self, raw_roles: Any) -> bool:
        if not isinstance(raw_roles, (list, tuple, set, frozenset)):
            return False
        return any(role == self.admin_role for role in raw_roles)

    @staticmethod
    def _identity_error(*, code: SecurityErrorCode, actor_id: str) -> SecurityFailure:
        return SecurityFailure(code=code, actor_id=actor_id)

    @staticmethod
    def _token_invalid_error() -> SecurityFailure:
        return SecurityFailure(code="TOKEN_INVALID")


AuthenticatedTokenRequesterResolver = DelegatedPrincipalResolver
