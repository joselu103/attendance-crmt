"""Black-box coverage for requester-scoped latest attendance and summaries."""

import asyncio
from dataclasses import replace
from datetime import datetime

import httpx

from attendance_crmt.audit import AuditEvent
from attendance_crmt.authentication import VerifiedDelegatedAccessToken
from attendance_crmt.identity import AuthenticatedTokenRequesterResolver
from attendance_crmt.models import AttendanceLog, Location
from attendance_crmt.rest import create_app

CORRELATION_ID = "11111111-1111-1111-1111-111111111111"
LATEST_ROUTE = "/api/v1/me/attendance-events/latest"
SUMMARY_ROUTE = "/api/v1/me/attendance-summary"


class StaticTokenVerifier:
    """Return one verified delegated user token for the requester."""

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


def test_requester_latest_event_is_server_scoped_and_orders_by_latest_check_in(
    server_dependencies, employee_factory, audit_session_factory
) -> None:
    requester = employee_factory.build(izvajalec_id=42, email="person@example.com")
    other = employee_factory.build(izvajalec_id=43, email="other@example.com")
    with server_dependencies.attendance_session_factory() as session:
        session.add_all(
            [
                requester,
                other,
                AttendanceLog(
                    att_id=100,
                    att_user_id=42,
                    att_in=datetime(2026, 8, 10, 8, 0),  # noqa: DTZ001
                ),
                AttendanceLog(
                    att_id=101,
                    att_user_id=42,
                    att_in=datetime(2026, 8, 11, 9, 0),  # noqa: DTZ001
                ),
                AttendanceLog(
                    att_id=102,
                    att_user_id=43,
                    att_in=datetime(2026, 8, 12, 10, 0),  # noqa: DTZ001
                ),
            ]
        )
        session.commit()

    response = _get(_app(server_dependencies), LATEST_ROUTE)

    assert response.status_code == 200
    assert response.json()["attendance_event_id"] == 101
    assert response.json()["employee_id"] == 42
    with audit_session_factory() as session:
        event = session.query(AuditEvent).one()
    assert event.tool_name == f"rest:{LATEST_ROUTE}"
    assert event.outcome == "success"


def test_requester_latest_event_returns_safe_not_found_for_empty_history(
    server_dependencies, employee_factory, audit_session_factory
) -> None:
    with server_dependencies.attendance_session_factory() as session:
        session.add(employee_factory.build(izvajalec_id=42, email="person@example.com"))
        session.commit()

    response = _get(_app(server_dependencies), LATEST_ROUTE)

    assert response.status_code == 404
    assert response.json() == {
        "code": "NOT_FOUND",
        "message": "The requested attendance resource was not found.",
    }
    with audit_session_factory() as session:
        event = session.query(AuditEvent).one()
    assert (event.outcome, event.error_code) == ("failure", "NOT_FOUND")


def test_requester_summary_is_isolated_and_groups_recorded_time_by_month_and_location(
    server_dependencies, employee_factory
) -> None:
    requester = employee_factory.build(izvajalec_id=42, email="person@example.com")
    other = employee_factory.build(izvajalec_id=43, email="other@example.com")
    office = Location(lokacija_id=1, lokacija_opis="Office")
    home = Location(lokacija_id=2, lokacija_opis="Home")
    with server_dependencies.attendance_session_factory() as session:
        session.add_all(
            [
                requester,
                other,
                office,
                home,
                AttendanceLog(
                    att_id=100,
                    att_user_id=42,
                    att_location_id=1,
                    att_in=datetime(2026, 1, 31, 20, 0),  # noqa: DTZ001
                    att_out=datetime(2026, 2, 1, 4, 0),  # noqa: DTZ001
                ),
                AttendanceLog(
                    att_id=101,
                    att_user_id=42,
                    att_location_id=2,
                    att_in=datetime(2026, 2, 2, 8, 0),  # noqa: DTZ001
                    att_out=datetime(2026, 2, 2, 12, 0),  # noqa: DTZ001
                ),
                AttendanceLog(
                    att_id=102,
                    att_user_id=43,
                    att_location_id=1,
                    att_in=datetime(2026, 2, 2, 8, 0),  # noqa: DTZ001
                    att_out=datetime(2026, 2, 2, 18, 0),  # noqa: DTZ001
                ),
            ]
        )
        session.commit()

    response = _get(
        _app(server_dependencies),
        f"{SUMMARY_ROUTE}?start_date=2026-02-01&end_date=2026-02-28",
    )

    assert response.status_code == 200
    assert response.json() == {
        "start_date": "2026-02-01",
        "end_date": "2026-02-28",
        "total_recorded_hours": "8.0",
        "attendance_day_count": 2,
        "monthly": [
            {
                "month": "2026-02",
                "recorded_hours": "8.0",
                "attendance_day_count": 2,
            }
        ],
        "locations": [
            {"location": "Home", "recorded_hours": "4.0", "attendance_day_count": 1},
            {"location": "Office", "recorded_hours": "4.0", "attendance_day_count": 1},
        ],
    }


def test_requester_summary_accepts_366_days_and_rejects_a_longer_range(
    server_dependencies, employee_factory
) -> None:
    with server_dependencies.attendance_session_factory() as session:
        session.add(employee_factory.build(izvajalec_id=42, email="person@example.com"))
        session.commit()

    app = _app(server_dependencies)
    allowed = _get(app, f"{SUMMARY_ROUTE}?start_date=2024-01-01&end_date=2024-12-31")
    rejected = _get(app, f"{SUMMARY_ROUTE}?start_date=2024-01-01&end_date=2025-01-01")

    assert allowed.status_code == 200
    assert allowed.json()["total_recorded_hours"] == "0"
    assert rejected.status_code == 400
    assert rejected.json()["code"] == "INVALID_ARGUMENT"
