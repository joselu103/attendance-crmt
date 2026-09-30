"""Black-box REST coverage for administrative attendance-event listing."""

import asyncio
import json
from dataclasses import replace
from datetime import date, datetime

import httpx
from fastmcp.server.auth import AccessToken

from attendance_crmt.attendance.contracts import AttendanceEventQuery
from attendance_crmt.attendance.services import list_attendance_events
from attendance_crmt.audit import AuditEvent
from attendance_crmt.identity import AuthenticatedTokenRequesterResolver, Principal
from attendance_crmt.models import AttendanceLog
from attendance_crmt.rest import create_app

CORRELATION_ID = "11111111-1111-1111-1111-111111111111"
ROUTE = "/api/v1/employees/42/attendance-events"


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


def _seed_attendance_events(server_dependencies, employee_factory) -> None:
    admin = employee_factory.build(izvajalec_id=1, email="admin@example.com")
    employee = employee_factory.build(izvajalec_id=42, email="person@example.com")
    with server_dependencies.attendance_session_factory() as session:
        session.add_all(
            [
                admin,
                employee,
                AttendanceLog(
                    att_id=100,
                    att_user_id=42,
                    att_in=datetime(2026, 8, 10, 8, 0),  # noqa: DTZ001
                ),
                AttendanceLog(
                    att_id=101,
                    att_user_id=42,
                    att_in=datetime(2026, 8, 11, 8, 0),  # noqa: DTZ001
                ),
            ]
        )
        session.commit()


def test_administrator_event_list_matches_service_and_audits_success(
    server_dependencies, employee_factory, audit_session_factory
) -> None:
    _seed_attendance_events(server_dependencies, employee_factory)

    response = _get(
        _app(server_dependencies, roles=["attendance.admin"]),
        f"{ROUTE}?start_date=2026-08-01&end_date=2026-08-31&limit=1",
        headers=_headers(),
    )

    expected = list_attendance_events(
        requester=Principal(
            actor_id="33333333-3333-3333-3333-333333333333:"
            "44444444-4444-4444-4444-444444444444",
            employee_id=1,
            roles=frozenset({"employee", "admin"}),
        ),
        session_factory=server_dependencies.attendance_session_factory,
        query=AttendanceEventQuery(
            employee_id=42,
            start_date=date(2026, 8, 1),
            end_date=date(2026, 8, 31),
            limit=1,
        ),
    )

    assert response.status_code == 200
    assert response.json() == json.loads(expected.model_dump_json())
    assert response.headers["X-Attendance-API-Contract-Version"] == "1.0.0"
    with audit_session_factory() as session:
        event = session.query(AuditEvent).one()
    assert event.correlation_id == CORRELATION_ID
    assert event.tool_name == "rest:/api/v1/employees/{employee_id}/attendance-events"
    assert event.outcome == "success"
    assert event.error_code is None
    assert event.request_json == "{}"


def test_administrator_event_list_denies_non_administrators_and_hides_invalid_input(
    server_dependencies, employee_factory, audit_session_factory
) -> None:
    _seed_attendance_events(server_dependencies, employee_factory)
    app = _app(server_dependencies, roles=[])

    forbidden = _get(
        app,
        f"{ROUTE}?start_date=2026-08-10&end_date=2026-08-10",
        headers=_headers(),
    )
    invalid = _get(
        _app(server_dependencies, roles=["attendance.admin"]),
        f"{ROUTE}?start_date=2026-08-10&end_date=token%3Dsecret",
        headers=_headers(),
    )
    over_range = _get(
        _app(server_dependencies, roles=["attendance.admin"]),
        f"{ROUTE}?start_date=2026-08-01&end_date=2026-09-01",
        headers=_headers(),
    )

    assert forbidden.status_code == 403
    assert forbidden.json() == {
        "code": "FORBIDDEN",
        "message": "You do not have permission to do that.",
    }
    assert invalid.status_code == 400
    assert invalid.json() == {
        "code": "INVALID_ARGUMENT",
        "message": "Check the attendance date range and pagination values and try again.",
    }
    assert over_range.status_code == 400
    assert over_range.json()["code"] == "INVALID_ARGUMENT"
    assert "token=secret" not in invalid.text
    with audit_session_factory() as session:
        events = session.query(AuditEvent).order_by(AuditEvent.event_id).all()
    assert [(event.outcome, event.error_code) for event in events] == [
        ("failure", "FORBIDDEN"),
        ("failure", "INVALID_ARGUMENT"),
        ("failure", "INVALID_ARGUMENT"),
    ]
    assert all(event.correlation_id == CORRELATION_ID for event in events)
    assert all(event.request_json == "{}" for event in events)


def test_administrator_event_list_rejects_missing_correlation_before_access(
    server_dependencies, employee_factory, audit_session_factory
) -> None:
    _seed_attendance_events(server_dependencies, employee_factory)

    response = _get(
        _app(server_dependencies, roles=["attendance.admin"]),
        f"{ROUTE}?start_date=2026-08-10&end_date=2026-08-10",
        headers=[("Authorization", "Bearer delegated-token")],
    )

    assert response.status_code == 400
    assert response.json() == {
        "code": "CORRELATION_ID_INVALID",
        "message": "The request correlation ID is missing or invalid.",
    }
    with audit_session_factory() as session:
        assert session.query(AuditEvent).count() == 0
