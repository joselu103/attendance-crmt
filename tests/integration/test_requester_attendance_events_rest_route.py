"""Black-box REST coverage for requester-scoped attendance events."""

import asyncio
import json
from dataclasses import replace
from datetime import date, datetime

import httpx

from attendance_crmt.attendance.contracts import MyAttendanceEventQuery
from attendance_crmt.attendance.services import list_my_attendance_events
from attendance_crmt.audit import AuditEvent
from attendance_crmt.authentication import VerifiedDelegatedAccessToken
from attendance_crmt.identity import AuthenticatedTokenRequesterResolver, Principal
from attendance_crmt.models import AttendanceLog
from attendance_crmt.rest import create_app

CORRELATION_ID = "11111111-1111-1111-1111-111111111111"
ROUTE = "/api/v1/me/attendance-events"


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


def test_requester_events_are_server_scoped_and_match_the_application_service(
    server_dependencies, employee_factory, audit_session_factory
) -> None:
    requester_employee = employee_factory.build(
        izvajalec_id=42, email="person@example.com"
    )
    other_employee = employee_factory.build(izvajalec_id=43, email="other@example.com")
    with server_dependencies.attendance_session_factory() as session:
        session.add_all(
            [
                requester_employee,
                other_employee,
                AttendanceLog(
                    att_id=100,
                    att_user_id=42,
                    att_in=datetime(2026, 8, 10, 8, 0),  # noqa: DTZ001
                    att_out=datetime(2026, 8, 10, 16, 0),  # noqa: DTZ001
                ),
                AttendanceLog(
                    att_id=101,
                    att_user_id=43,
                    att_in=datetime(2026, 8, 10, 8, 0),  # noqa: DTZ001
                ),
            ]
        )
        session.commit()

    response = _get(
        _app(server_dependencies),
        f"{ROUTE}?start_date=2026-08-10&end_date=2026-08-10&employee_id=43",
        headers=_headers(),
    )

    expected = list_my_attendance_events(
        requester=Principal(
            actor_id="33333333-3333-3333-3333-333333333333:"
            "44444444-4444-4444-4444-444444444444",
            employee_id=42,
            roles=frozenset({"employee"}),
        ),
        session_factory=server_dependencies.attendance_session_factory,
        query=MyAttendanceEventQuery(
            start_date=date(2026, 8, 10), end_date=date(2026, 8, 10)
        ),
    )

    assert response.status_code == 200
    assert response.json() == json.loads(expected.model_dump_json())
    assert [event["employee_id"] for event in response.json()["items"]] == [42]
    assert response.headers["X-Attendance-API-Contract-Version"] == "1.0.0"
    with audit_session_factory() as session:
        event = session.query(AuditEvent).one()
    assert event.correlation_id == CORRELATION_ID
    assert event.tool_name == f"rest:{ROUTE}"
    assert event.outcome == "success"
    assert event.request_json == "{}"


def test_requester_events_enforce_pagination_and_safe_date_validation(
    server_dependencies, employee_factory, audit_session_factory
) -> None:
    requester_employee = employee_factory.build(
        izvajalec_id=42, email="person@example.com"
    )
    with server_dependencies.attendance_session_factory() as session:
        session.add_all(
            [
                requester_employee,
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

    app = _app(server_dependencies)
    paged = _get(
        app,
        f"{ROUTE}?start_date=2026-08-01&end_date=2026-08-31&limit=1",
        headers=_headers(),
    )
    invalid = _get(
        app,
        f"{ROUTE}?start_date=2026-08-01&end_date=2026-09-01&limit=token%3Dsecret",
        headers=_headers(),
    )

    assert paged.status_code == 200
    assert paged.json()["limit"] == 1
    assert paged.json()["offset"] == 0
    assert paged.json()["next_offset"] == 1
    assert [event["attendance_event_id"] for event in paged.json()["items"]] == [100]
    assert invalid.status_code == 400
    assert invalid.json() == {
        "code": "INVALID_ARGUMENT",
        "message": "Check the attendance date range and pagination values and try again.",
    }
    assert "token=secret" not in invalid.text
    with audit_session_factory() as session:
        events = session.query(AuditEvent).order_by(AuditEvent.event_id).all()
    assert [(event.outcome, event.error_code) for event in events] == [
        ("success", None),
        ("failure", "INVALID_ARGUMENT"),
    ]
    assert all(event.tool_name == f"rest:{ROUTE}" for event in events)


def test_requester_events_require_a_delegated_bearer_before_access(
    server_dependencies, audit_session_factory
) -> None:
    response = _get(
        _app(server_dependencies),
        f"{ROUTE}?start_date=2026-08-10&end_date=2026-08-10",
        headers=[("X-Correlation-ID", CORRELATION_ID)],
    )

    assert response.status_code == 401
    assert response.json() == {
        "code": "AUTHENTICATION_REQUIRED",
        "message": "Please sign in to use Attendance.",
    }
    with audit_session_factory() as session:
        event = session.query(AuditEvent).one()
    assert event.actor_id == "unresolved"
    assert event.tool_name == f"rest:{ROUTE}"
    assert event.request_json == "{}"
    assert event.error_code == "AUTHENTICATION_REQUIRED"


def test_requester_events_reject_invalid_correlation_before_access(
    server_dependencies, employee_factory, audit_session_factory
) -> None:
    employee = employee_factory.build(izvajalec_id=42, email="person@example.com")
    with server_dependencies.attendance_session_factory() as session:
        session.add(employee)
        session.commit()

    response = _get(
        _app(server_dependencies),
        f"{ROUTE}?start_date=2026-08-10&end_date=2026-08-10",
        headers=[("Authorization", "Bearer delegated-token")],
    )

    assert response.status_code == 400
    assert response.json() == {
        "code": "CORRELATION_ID_INVALID",
        "message": "The request correlation ID is missing or invalid.",
    }
    with audit_session_factory() as session:
        event = session.query(AuditEvent).one()
    assert event.actor_id == "unresolved"
    assert event.tool_name == f"rest:{ROUTE}"
    assert event.request_json == "{}"
    assert event.error_code == "CORRELATION_ID_INVALID"
