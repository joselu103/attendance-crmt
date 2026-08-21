"""Requester identity abstractions independent of server composition."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from sqlalchemy import func, select
from sqlalchemy.exc import MultipleResultsFound, NoResultFound
from sqlalchemy.orm import Session, sessionmaker

from attendance_crmt.models import Employee


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
