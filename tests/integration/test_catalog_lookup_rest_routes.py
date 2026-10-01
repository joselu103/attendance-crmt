"""Black-box REST coverage for authenticated catalog lookup routes."""

import asyncio
import json
from dataclasses import replace

import httpx
from sqlalchemy import select

from attendance_crmt.audit import AuditEvent
from attendance_crmt.authentication import VerifiedDelegatedAccessToken
from attendance_crmt.catalog.contracts import EmployeePageQuery
from attendance_crmt.catalog.services import (
    get_employee,
    list_active_employees,
    list_locations,
    list_punch_types,
)
from attendance_crmt.identity import AuthenticatedTokenRequesterResolver
from attendance_crmt.models import Location, PunchType
from attendance_crmt.rest import create_app

CORRELATION_ID = "11111111-1111-1111-1111-111111111111"
EMPLOYEES_ROUTE = "/api/v1/employees"
PUNCH_TYPES_ROUTE = "/api/v1/punch-types"
LOCATIONS_ROUTE = "/api/v1/locations"


class StaticTokenVerifier:
    """Return one already-verified delegated user token."""

    async def verify_token(self, token: str) -> VerifiedDelegatedAccessToken | None:
        if token != "delegated-token":
            return None
        return VerifiedDelegatedAccessToken(
            token=token,
            client_id="22222222-2222-2222-2222-222222222222",
            scopes=["attendance.access"],
            claims={
                "tid": "33333333-3333-3333-3333-333333333333",
                "oid": "44444444-4444-4444-4444-444444444444",
                "preferred_username": "person@example.com",
                "roles": [],
            },
        )


def _get(app, path: str, *, headers: list[tuple[str, str]]) -> httpx.Response:
    async def request() -> httpx.Response:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://test",
        ) as client:
            return await client.get(path, headers=headers)

    return asyncio.run(request())


def _headers() -> list[tuple[str, str]]:
    return [
        ("Authorization", "Bearer delegated-token"),
        ("X-Correlation-ID", CORRELATION_ID),
    ]


def _app(server_dependencies):
    resolver = AuthenticatedTokenRequesterResolver(
        session_factory=server_dependencies.attendance_session_factory,
        admin_role="attendance.admin",
    )
    return create_app(
        replace(
            server_dependencies,
            auth_provider=StaticTokenVerifier(),  # type: ignore[arg-type]
            principal_resolver=resolver,
        )
    )


def test_employee_routes_match_catalog_services_and_preserve_pagination(
    server_dependencies, employee_factory, audit_session_factory
) -> None:
    requester = employee_factory.build(izvajalec_id=42, email="person@example.com")
    first = employee_factory.build(izvajalec_id=43, priimek="Adams", ime="Alice")
    second = employee_factory.build(izvajalec_id=44, priimek="Brown", ime="Bob")
    inactive = employee_factory.build(izvajalec_id=45, active=0)
    with server_dependencies.attendance_session_factory() as session:
        session.add_all([requester, first, second, inactive])
        session.commit()

    app = _app(server_dependencies)
    page = _get(app, f"{EMPLOYEES_ROUTE}?limit=1&offset=0", headers=_headers())
    employee = _get(app, f"{EMPLOYEES_ROUTE}/{first.izvajalec_id}", headers=_headers())

    expected_page = list_active_employees(
        session_factory=server_dependencies.attendance_session_factory,
        query=EmployeePageQuery(limit=1, offset=0),
    )
    expected_employee = get_employee(
        session_factory=server_dependencies.attendance_session_factory,
        employee_id=first.izvajalec_id,
    )
    assert page.status_code == 200
    assert page.json() == json.loads(expected_page.model_dump_json())
    assert page.headers["X-Attendance-API-Contract-Version"] == "1.0.0"
    assert employee.status_code == 200
    assert employee.json() == json.loads(expected_employee.model_dump_json())
    with audit_session_factory() as session:
        events = session.scalars(select(AuditEvent).order_by(AuditEvent.event_id)).all()
    assert [(event.tool_name, event.outcome, event.error_code) for event in events] == [
        (f"rest:{EMPLOYEES_ROUTE}", "success", None),
        (f"rest:{EMPLOYEES_ROUTE}/{{employee_id}}", "success", None),
    ]
    assert all(event.correlation_id == CORRELATION_ID for event in events)
    assert all(event.request_json == "{}" for event in events)


def test_punch_type_and_location_routes_match_immutable_catalog_contracts(
    server_dependencies, employee_factory, audit_session_factory
) -> None:
    requester = employee_factory.build(izvajalec_id=42, email="person@example.com")
    company = Location(lokacija_id=2, lokacija_opis="Company")
    other = Location(lokacija_id=5, lokacija_opis="Other")
    office = PunchType(punch_type_id=1, punch_type_desc="Office", active=1)
    remote = PunchType(punch_type_id=2, punch_type_desc="Remote", active=0)
    with server_dependencies.attendance_session_factory() as session:
        session.add_all([requester, company, other, office, remote])
        session.commit()

    app = _app(server_dependencies)
    active_punch_types = _get(app, PUNCH_TYPES_ROUTE, headers=_headers())
    all_punch_types = _get(
        app, f"{PUNCH_TYPES_ROUTE}?active_only=false", headers=_headers()
    )
    locations = _get(app, LOCATIONS_ROUTE, headers=_headers())

    assert active_punch_types.status_code == 200
    assert active_punch_types.json() == json.loads(
        json.dumps(
            [
                item.model_dump()
                for item in list_punch_types(
                    session_factory=server_dependencies.attendance_session_factory
                )
            ]
        )
    )
    assert all_punch_types.status_code == 200
    assert all_punch_types.json() == json.loads(
        json.dumps(
            [
                item.model_dump()
                for item in list_punch_types(
                    session_factory=server_dependencies.attendance_session_factory,
                    active_only=False,
                )
            ]
        )
    )
    assert locations.status_code == 200
    assert locations.json() == json.loads(
        json.dumps(
            [
                item.model_dump()
                for item in list_locations(
                    session_factory=server_dependencies.attendance_session_factory
                )
            ]
        )
    )
    with audit_session_factory() as session:
        events = session.scalars(select(AuditEvent).order_by(AuditEvent.event_id)).all()
    assert [event.tool_name for event in events] == [
        f"rest:{PUNCH_TYPES_ROUTE}",
        f"rest:{PUNCH_TYPES_ROUTE}",
        f"rest:{LOCATIONS_ROUTE}",
    ]
    assert all(event.outcome == "success" for event in events)
    assert all(event.correlation_id == CORRELATION_ID for event in events)


def test_catalog_routes_require_authentication_and_return_safe_audited_failures(
    server_dependencies, employee_factory, audit_session_factory
) -> None:
    requester = employee_factory.build(izvajalec_id=42, email="person@example.com")
    with server_dependencies.attendance_session_factory() as session:
        session.add(requester)
        session.commit()

    app = _app(server_dependencies)
    missing_auth = _get(
        app,
        EMPLOYEES_ROUTE,
        headers=[("X-Correlation-ID", CORRELATION_ID)],
    )
    invalid_page = _get(
        app,
        f"{EMPLOYEES_ROUTE}?limit=token%3Dsecret",
        headers=_headers(),
    )
    not_found = _get(app, f"{EMPLOYEES_ROUTE}/999", headers=_headers())

    assert missing_auth.status_code == 401
    assert missing_auth.json() == {
        "code": "AUTHENTICATION_REQUIRED",
        "message": "Please sign in to use Attendance.",
    }
    assert invalid_page.status_code == 400
    assert invalid_page.json() == {
        "code": "INVALID_ARGUMENT",
        "message": "Check the attendance date range and pagination values and try again.",
    }
    assert "token=secret" not in invalid_page.text
    assert not_found.status_code == 404
    assert not_found.json() == {
        "code": "NOT_FOUND",
        "message": "The requested attendance resource was not found.",
    }
    with audit_session_factory() as session:
        events = session.scalars(select(AuditEvent).order_by(AuditEvent.event_id)).all()
    assert [(event.tool_name, event.outcome, event.error_code) for event in events] == [
        (f"rest:{EMPLOYEES_ROUTE}", "failure", "AUTHENTICATION_REQUIRED"),
        (f"rest:{EMPLOYEES_ROUTE}", "failure", "INVALID_ARGUMENT"),
        (f"rest:{EMPLOYEES_ROUTE}/{{employee_id}}", "failure", "NOT_FOUND"),
    ]
    assert all(event.correlation_id == CORRELATION_ID for event in events)
    assert all(event.request_json == "{}" for event in events)
