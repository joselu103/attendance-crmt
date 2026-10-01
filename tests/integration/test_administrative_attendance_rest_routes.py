"""Black-box REST coverage for administrative attendance detail reads."""

import asyncio
from dataclasses import replace
from datetime import datetime
from decimal import Decimal

import httpx
import pytest

from attendance_crmt.audit import AuditEvent
from attendance_crmt.authentication import VerifiedDelegatedAccessToken
from attendance_crmt.identity import AuthenticatedTokenRequesterResolver
from attendance_crmt.models import AttendanceLog, PlannedWork
from attendance_crmt.rest import create_app

CORRELATION_ID = "11111111-1111-1111-1111-111111111111"
DETAIL_ROUTE = "/api/v1/attendance-events/100"
DAILY_ROUTE = "/api/v1/employees/42/daily-attendance?day=2026-08-10"
PLANNED_WORK_ROUTE = (
    "/api/v1/employees/42/planned-work?start_date=2026-08-10&end_date=2026-08-12"
)


class StaticTokenVerifier:
    """Return an already-verified delegated token with selected CRMT roles."""

    def __init__(self, *, roles: list[str]) -> None:
        self._roles = roles

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
                headers=[
                    ("Authorization", "Bearer delegated-token"),
                    ("X-Correlation-ID", CORRELATION_ID),
                ],
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
        )
    )


def _add_attendance_data(server_dependencies, employee_factory) -> None:
    employee = employee_factory.build(izvajalec_id=42, email="person@example.com")
    with server_dependencies.attendance_session_factory() as session:
        session.add_all(
            [
                employee,
                AttendanceLog(
                    att_id=100,
                    att_user_id=42,
                    att_in=datetime(2026, 8, 10, 8, 0),  # noqa: DTZ001
                    att_out=datetime(2026, 8, 10, 16, 0),  # noqa: DTZ001
                    att_edited=1,
                    user_id="admin",
                    data_source="MCP",
                ),
                PlannedWork(
                    izvajalec_id=42,
                    datum_id=datetime(2026, 8, 10),  # noqa: DTZ001
                    att_planirano_ur_va=Decimal("7.50"),
                ),
            ]
        )
        session.commit()


def test_administrative_attendance_reads_return_service_results_and_audit(
    server_dependencies, employee_factory, audit_session_factory
) -> None:
    _add_attendance_data(server_dependencies, employee_factory)
    app = _app(server_dependencies, roles=["attendance.admin"])

    detail = _get(app, DETAIL_ROUTE)
    daily = _get(app, DAILY_ROUTE)
    planned_work = _get(app, PLANNED_WORK_ROUTE)

    assert detail.status_code == 200
    assert detail.json() == {
        "attendance_event_id": 100,
        "employee_id": 42,
        "punch_type": None,
        "location": None,
        "checked_in_at": "2026-08-10T08:00:00+02:00",
        "checked_out_at": "2026-08-10T16:00:00+02:00",
        "note": None,
        "edited": True,
        "recorded_at": None,
        "modified_at": None,
        "modified_by": "admin",
        "data_source": "MCP",
    }
    assert daily.status_code == 200
    assert daily.json()["balance_hours"] == "0.50"
    assert [event["attendance_event_id"] for event in daily.json()["events"]] == [100]
    assert planned_work.status_code == 200
    assert planned_work.json() == {
        "employee_id": 42,
        "start_date": "2026-08-10",
        "end_date": "2026-08-12",
        "items": [{"day": "2026-08-10", "planned_hours": "7.50"}],
    }
    assert all(
        response.headers["X-Attendance-API-Contract-Version"] == "1.0.0"
        for response in (detail, daily, planned_work)
    )
    with audit_session_factory() as session:
        events = session.query(AuditEvent).order_by(AuditEvent.event_id).all()
    assert [(event.tool_name, event.outcome, event.error_code) for event in events] == [
        ("rest:/api/v1/attendance-events/{attendance_event_id}", "success", None),
        ("rest:/api/v1/employees/{employee_id}/daily-attendance", "success", None),
        ("rest:/api/v1/employees/{employee_id}/planned-work", "success", None),
    ]
    assert all(event.correlation_id == CORRELATION_ID for event in events)
    assert all(event.request_json == "{}" for event in events)


@pytest.mark.parametrize("route", [DETAIL_ROUTE, DAILY_ROUTE, PLANNED_WORK_ROUTE])
def test_administrative_attendance_reads_deny_non_administrators(
    route, server_dependencies, employee_factory, audit_session_factory
) -> None:
    _add_attendance_data(server_dependencies, employee_factory)

    response = _get(_app(server_dependencies, roles=[]), route)

    assert response.status_code == 403
    assert response.json() == {
        "code": "FORBIDDEN",
        "message": "You do not have permission to do that.",
    }
    with audit_session_factory() as session:
        event = session.query(AuditEvent).one()
    assert event.correlation_id == CORRELATION_ID
    assert event.outcome == "failure"
    assert event.error_code == "FORBIDDEN"
    assert event.request_json == "{}"


def test_administrative_attendance_reads_return_safe_failures_and_audit(
    server_dependencies, employee_factory, audit_session_factory
) -> None:
    _add_attendance_data(server_dependencies, employee_factory)
    app = _app(server_dependencies, roles=["attendance.admin"])

    missing = _get(app, "/api/v1/attendance-events/999")
    invalid = _get(
        app,
        "/api/v1/employees/42/planned-work?start_date=2026-08-10&"
        "end_date=token%3Dsecret",
    )

    assert missing.status_code == 404
    assert missing.json() == {
        "code": "NOT_FOUND",
        "message": "The requested attendance resource was not found.",
    }
    assert invalid.status_code == 400
    assert invalid.json() == {
        "code": "INVALID_ARGUMENT",
        "message": "Check the attendance date range and pagination values and try again.",
    }
    assert "token=secret" not in invalid.text
    with audit_session_factory() as session:
        events = session.query(AuditEvent).order_by(AuditEvent.event_id).all()
    assert [(event.outcome, event.error_code) for event in events] == [
        ("failure", "NOT_FOUND"),
        ("failure", "INVALID_ARGUMENT"),
    ]
