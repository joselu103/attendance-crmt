import json
from typing import Any

import pytest
from fastmcp.exceptions import ToolError
from fastmcp.server.auth import AccessToken

from attendance_crmt.identity import (
    AuthenticatedTokenRequesterResolver,
    EmailIdentityAmbiguousError,
    EmailIdentityUnmappedError,
    resolve_active_employee_id_for_email,
)
from attendance_crmt.security_errors import (
    IDENTITY_AMBIGUOUS_MESSAGE,
    IDENTITY_UNMAPPED_MESSAGE,
    TOKEN_INVALID_MESSAGE,
)


def test_resolve_active_employee_id_for_email_returns_unique_active_employee(
    employee_session_factory,
    employee_factory,
) -> None:
    employee = employee_factory.build(
        izvajalec_id=42,
        email="person@example.com",
        active=1,
    )
    with employee_session_factory() as session:
        session.add(employee)
        session.commit()

    employee_id = resolve_active_employee_id_for_email(
        session_factory=employee_session_factory,
        email="  PERSON@example.com  ",
    )

    assert employee_id == 42


def test_resolve_active_employee_id_for_email_rejects_inactive_employee(
    employee_session_factory,
    employee_factory,
) -> None:
    employee = employee_factory.build(email="person@example.com", active=0)
    with employee_session_factory() as session:
        session.add(employee)
        session.commit()

    with pytest.raises(EmailIdentityUnmappedError):
        resolve_active_employee_id_for_email(
            session_factory=employee_session_factory,
            email="person@example.com",
        )


def test_resolve_active_employee_id_for_email_rejects_duplicate_active_email(
    employee_session_factory,
    employee_factory,
) -> None:
    employees = employee_factory.build_batch(2, email="person@example.com", active=1)
    with employee_session_factory() as session:
        session.add_all(employees)
        session.commit()

    with pytest.raises(EmailIdentityAmbiguousError):
        resolve_active_employee_id_for_email(
            session_factory=employee_session_factory,
            email="person@example.com",
        )


def _access_token(
    *,
    email: str = "person@example.com",
    roles: Any = None,
) -> AccessToken:
    return AccessToken(
        token="validated-test-token",
        client_id="22222222-2222-2222-2222-222222222222",
        scopes=["attendance.access"],
        subject="11111111-1111-1111-1111-111111111111:33333333-3333-3333-3333-333333333333",
        claims={
            "tid": "11111111-1111-1111-1111-111111111111",
            "oid": "33333333-3333-3333-3333-333333333333",
            "preferred_username": email,
            "roles": roles if roles is not None else [],
        },
    )


def _authenticated_resolver(
    *,
    employee_session_factory,
    access_token: AccessToken | None,
) -> AuthenticatedTokenRequesterResolver:
    return AuthenticatedTokenRequesterResolver(
        session_factory=employee_session_factory,
        admin_role="attendance.admin",
        access_token_provider=lambda: access_token,
    )


def test_authenticated_requester_maps_validated_claims_to_active_employee(
    employee_session_factory,
    employee_factory,
) -> None:
    employee = employee_factory.build(
        izvajalec_id=42,
        email="person@example.com",
        active=1,
    )
    with employee_session_factory() as session:
        session.add(employee)
        session.commit()
    resolver = _authenticated_resolver(
        employee_session_factory=employee_session_factory,
        access_token=_access_token(
            email="  PERSON@example.com  ",
            roles=["attendance.admin"],
        ),
    )

    requester = resolver.resolve(context=None)

    assert requester.actor_id == (
        "11111111-1111-1111-1111-111111111111:33333333-3333-3333-3333-333333333333"
    )
    assert requester.employee_id == 42
    assert requester.roles == frozenset({"employee", "admin"})


@pytest.mark.parametrize("roles", [["Attendance.Admin"], "attendance.admin"])
def test_authenticated_requester_does_not_trust_malformed_or_similar_admin_role(
    employee_session_factory,
    employee_factory,
    roles: Any,
) -> None:
    employee = employee_factory.build(email="person@example.com", active=1)
    with employee_session_factory() as session:
        session.add(employee)
        session.commit()
    resolver = _authenticated_resolver(
        employee_session_factory=employee_session_factory,
        access_token=_access_token(roles=roles),
    )

    requester = resolver.resolve(context=None)

    assert requester.roles == frozenset({"employee"})


def test_authenticated_requester_returns_identity_unmapped(
    employee_session_factory,
) -> None:
    resolver = _authenticated_resolver(
        employee_session_factory=employee_session_factory,
        access_token=_access_token(),
    )

    with pytest.raises(ToolError) as error:
        resolver.resolve(context=None)

    assert json.loads(str(error.value)) == {
        "code": "IDENTITY_UNMAPPED",
        "message": IDENTITY_UNMAPPED_MESSAGE,
    }


def test_authenticated_requester_returns_identity_ambiguous(
    employee_session_factory,
    employee_factory,
) -> None:
    employees = employee_factory.build_batch(2, email="person@example.com", active=1)
    with employee_session_factory() as session:
        session.add_all(employees)
        session.commit()
    resolver = _authenticated_resolver(
        employee_session_factory=employee_session_factory,
        access_token=_access_token(),
    )

    with pytest.raises(ToolError) as error:
        resolver.resolve(context=None)

    assert json.loads(str(error.value)) == {
        "code": "IDENTITY_AMBIGUOUS",
        "message": IDENTITY_AMBIGUOUS_MESSAGE,
    }


@pytest.mark.parametrize(
    "access_token",
    [
        None,
        _access_token(email="   "),
        AccessToken(
            token="validated-test-token",
            client_id="22222222-2222-2222-2222-222222222222",
            scopes=["attendance.access"],
            claims={"preferred_username": "person@example.com"},
        ),
        AccessToken(
            token="validated-test-token",
            client_id="22222222-2222-2222-2222-222222222222",
            scopes=["attendance.access"],
            claims={
                "tid": "not-a-tenant-uuid",
                "oid": "33333333-3333-3333-3333-333333333333",
                "preferred_username": "person@example.com",
            },
        ),
        AccessToken(
            token="validated-test-token",
            client_id="22222222-2222-2222-2222-222222222222",
            scopes=["attendance.access"],
            claims={
                "tid": "11111111-1111-1111-1111-111111111111",
                "oid": "33333333-3333-3333-3333-333333333333",
                "preferred_username": None,
            },
        ),
    ],
)
def test_authenticated_requester_rejects_missing_validated_identity_claims(
    employee_session_factory,
    access_token: AccessToken | None,
) -> None:
    resolver = _authenticated_resolver(
        employee_session_factory=employee_session_factory,
        access_token=access_token,
    )

    with pytest.raises(ToolError) as error:
        resolver.resolve(context=None)

    assert json.loads(str(error.value)) == {
        "code": "TOKEN_INVALID",
        "message": TOKEN_INVALID_MESSAGE,
    }
