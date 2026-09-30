"""Black-box coverage for privileged exact employee resolution."""

import asyncio
from dataclasses import replace

import httpx
from fastmcp.server.auth import AccessToken
from sqlalchemy import select

from attendance_crmt.audit import AuditEvent
from attendance_crmt.identity import AuthenticatedTokenRequesterResolver
from attendance_crmt.rest import create_app

CORRELATION_ID = "11111111-1111-1111-1111-111111111111"
ROUTE = "/api/v1/employees/resolve"


class StaticTokenVerifier:
    """Return an already-verified delegated token with selected CRMT roles."""

    def __init__(self, *, roles: list[str]) -> None:
        self._roles = roles

    async def verify_token(self, token: str) -> AccessToken | None:
        if token != "delegated-token":
            return None
        return AccessToken(
            token=token,
            client_id="22222222-2222-2222-2222-222222222222",
            scopes=["attendance.access"],
            claims={
                "tid": "33333333-3333-3333-3333-333333333333",
                "oid": "44444444-4444-4444-4444-444444444444",
                "preferred_username": "admin@example.com",
                "roles": self._roles,
            },
        )


def _get(app, path: str) -> httpx.Response:
    async def request() -> httpx.Response:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://test",
        ) as client:
            return await client.get(
                path,
                headers={
                    "Authorization": "Bearer delegated-token",
                    "X-Correlation-ID": CORRELATION_ID,
                },
            )

    return asyncio.run(request())


def _app(server_dependencies, *, roles: list[str]):
    resolver = AuthenticatedTokenRequesterResolver(
        session_factory=server_dependencies.attendance_session_factory,
        admin_role="attendance.admin",
    )
    return create_app(
        replace(
            server_dependencies,
            auth_provider=StaticTokenVerifier(roles=roles),  # type: ignore[arg-type]
            principal_resolver=resolver,
            requester_resolver=resolver,
        )
    )


def test_administrator_resolves_one_employee_by_each_exact_identifier(
    server_dependencies, employee_factory, audit_session_factory
) -> None:
    admin = employee_factory.build(izvajalec_id=1, email="admin@example.com")
    employee = employee_factory.build(
        izvajalec_id=42,
        username="target.user",
        email="target@example.com",
    )
    with server_dependencies.attendance_session_factory() as session:
        session.add_all([admin, employee])
        session.commit()

    app = _app(server_dependencies, roles=["attendance.admin"])
    responses = [
        _get(app, f"{ROUTE}?employee_id=42"),
        _get(app, f"{ROUTE}?username=target.user"),
        _get(app, f"{ROUTE}?email=target@example.com"),
    ]

    expected = {
        "employee_id": 42,
        "first_name": employee.ime,
        "last_name": employee.priimek,
        "username": "target.user",
        "email": "target@example.com",
        "active": employee.active,
    }
    assert all(response.status_code == 200 for response in responses)
    assert [response.json() for response in responses] == [expected, expected, expected]
    with audit_session_factory() as session:
        events = session.scalars(select(AuditEvent).order_by(AuditEvent.event_id)).all()
    assert [(event.tool_name, event.outcome, event.error_code) for event in events] == [
        ("rest:/api/v1/employees/resolve", "success", None),
        ("rest:/api/v1/employees/resolve", "success", None),
        ("rest:/api/v1/employees/resolve", "success", None),
    ]
    assert all(event.request_json == "{}" for event in events)


def test_resolver_requires_admin_one_exact_identifier_and_safe_absence(
    server_dependencies, employee_factory, audit_session_factory
) -> None:
    admin = employee_factory.build(izvajalec_id=1, email="admin@example.com")
    employee = employee_factory.build(izvajalec_id=42, username="target.user")
    with server_dependencies.attendance_session_factory() as session:
        session.add_all([admin, employee])
        session.commit()

    forbidden = _get(_app(server_dependencies, roles=[]), f"{ROUTE}?employee_id=42")
    missing = _get(_app(server_dependencies, roles=["attendance.admin"]), ROUTE)
    multiple = _get(
        _app(server_dependencies, roles=["attendance.admin"]),
        f"{ROUTE}?employee_id=42&username=target.user",
    )
    absent = _get(
        _app(server_dependencies, roles=["attendance.admin"]),
        f"{ROUTE}?email=nobody@example.com",
    )
    different_case = _get(
        _app(server_dependencies, roles=["attendance.admin"]),
        f"{ROUTE}?username=TARGET.USER",
    )

    assert forbidden.status_code == 403
    assert forbidden.json()["code"] == "FORBIDDEN"
    assert missing.status_code == 400
    assert missing.json()["code"] == "INVALID_ARGUMENT"
    assert multiple.status_code == 400
    assert multiple.json()["code"] == "INVALID_ARGUMENT"
    assert absent.status_code == 404
    assert absent.json()["code"] == "NOT_FOUND"
    assert different_case.status_code == 404
    assert different_case.json()["code"] == "NOT_FOUND"
    with audit_session_factory() as session:
        events = session.scalars(select(AuditEvent).order_by(AuditEvent.event_id)).all()
    assert [(event.outcome, event.error_code) for event in events] == [
        ("failure", "FORBIDDEN"),
        ("failure", "INVALID_ARGUMENT"),
        ("failure", "INVALID_ARGUMENT"),
        ("failure", "NOT_FOUND"),
        ("failure", "NOT_FOUND"),
    ]
