"""Black-box REST parity and bounded-loading coverage for reporting routes."""

import asyncio
import json
from dataclasses import replace
from datetime import date, datetime
from decimal import Decimal

import httpx
from sqlalchemy import event

from attendance_crmt.attendance.contracts import (
    AttendanceExceptionsQuery,
    CurrentAttendanceQuery,
    EmployeeAttendanceAnalysisQuery,
    OrganizationAttendanceAnalysisQuery,
)
from attendance_crmt.attendance.services import (
    get_attendance_exceptions,
    get_employee_attendance_analysis,
    get_employee_attendance_summary,
    get_organization_attendance_analysis,
    list_current_attendance,
)
from attendance_crmt.authentication import VerifiedDelegatedAccessToken
from attendance_crmt.identity import AuthenticatedTokenRequesterResolver, Principal
from attendance_crmt.models import AttendanceLog, PlannedWork, PunchType
from attendance_crmt.rest import create_app

CORRELATION_ID = "11111111-1111-1111-1111-111111111111"


class StaticTokenVerifier:
    """Return a verified delegated token with the requested administrative role."""

    async def verify_token(self, token: str) -> VerifiedDelegatedAccessToken | None:
        if token not in {"admin-token", "employee-token"}:
            return None
        return VerifiedDelegatedAccessToken(
            token=token,
            client_id="22222222-2222-2222-2222-222222222222",
            scopes=["attendance.access"],
            claims={
                "tid": "33333333-3333-3333-3333-333333333333",
                "oid": "44444444-4444-4444-4444-444444444444",
                "preferred_username": "admin@example.com",
                "roles": ["attendance.admin"] if token == "admin-token" else [],
            },
        )


def _get(app, path: str, *, token: str = "admin-token") -> httpx.Response:
    async def request() -> httpx.Response:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://test",
        ) as client:
            return await client.get(
                path,
                headers={
                    "Authorization": f"Bearer {token}",
                    "X-Correlation-ID": CORRELATION_ID,
                },
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


def _admin() -> Principal:
    return Principal(
        actor_id="33333333-3333-3333-3333-333333333333:"
        "44444444-4444-4444-4444-444444444444",
        employee_id=1,
        roles=frozenset({"employee", "admin"}),
    )


def _seed_reporting_data(server_dependencies, employee_factory) -> None:
    admin = employee_factory.build(izvajalec_id=1, email="admin@example.com")
    employee = employee_factory.build(izvajalec_id=2, priimek="Baker")
    with server_dependencies.attendance_session_factory() as session:
        session.add_all(
            [
                admin,
                employee,
                PlannedWork(
                    izvajalec_id=1,
                    datum_id=datetime(2026, 8, 14),  # noqa: DTZ001
                    att_planirano_ur_va=Decimal("8.00"),
                ),
                PlannedWork(
                    izvajalec_id=2,
                    datum_id=datetime(2026, 8, 14),  # noqa: DTZ001
                    att_planirano_ur_va=Decimal("8.00"),
                ),
                AttendanceLog(
                    att_id=10,
                    att_user_id=1,
                    att_in=datetime(2026, 8, 14, 8, 0),  # noqa: DTZ001
                    att_out=datetime(2026, 8, 14, 16, 0),  # noqa: DTZ001
                ),
                AttendanceLog(
                    att_id=11,
                    att_user_id=2,
                    att_in=datetime(2026, 8, 14, 8, 0),  # noqa: DTZ001
                ),
            ]
        )
        session.commit()


def test_reporting_routes_match_application_services(
    server_dependencies, employee_factory
) -> None:
    _seed_reporting_data(server_dependencies, employee_factory)
    app = _app(server_dependencies)
    query_date = "start_date=2026-08-14&end_date=2026-08-14"

    responses_and_expected = [
        (
            _get(app, "/api/v1/attendance/current?as_of=2026-08-14T12:00:00"),
            list_current_attendance(
                session_factory=server_dependencies.attendance_session_factory,
                query=CurrentAttendanceQuery(
                    as_of=datetime(2026, 8, 14, 12, 0)  # noqa: DTZ001
                ),
                include_unknown=False,
            ),
        ),
        (
            _get(app, f"/api/v1/employees/1/attendance-summary?{query_date}"),
            get_employee_attendance_summary(
                requester=_admin(),
                session_factory=server_dependencies.attendance_session_factory,
                query=EmployeeAttendanceAnalysisQuery(
                    employee_id=1,
                    start_date=date(2026, 8, 14),
                    end_date=date(2026, 8, 14),
                ),
            ),
        ),
        (
            _get(app, f"/api/v1/employees/1/attendance-analysis?{query_date}"),
            get_employee_attendance_analysis(
                requester=_admin(),
                session_factory=server_dependencies.attendance_session_factory,
                query=EmployeeAttendanceAnalysisQuery(
                    employee_id=1,
                    start_date=date(2026, 8, 14),
                    end_date=date(2026, 8, 14),
                ),
            ),
        ),
        (
            _get(app, f"/api/v1/attendance/organization-analysis?{query_date}"),
            get_organization_attendance_analysis(
                requester=_admin(),
                session_factory=server_dependencies.attendance_session_factory,
                query=OrganizationAttendanceAnalysisQuery(
                    start_date=date(2026, 8, 14), end_date=date(2026, 8, 14)
                ),
            ),
        ),
        (
            _get(app, f"/api/v1/attendance/exceptions?{query_date}"),
            get_attendance_exceptions(
                requester=_admin(),
                session_factory=server_dependencies.attendance_session_factory,
                query=AttendanceExceptionsQuery(
                    start_date=date(2026, 8, 14), end_date=date(2026, 8, 14)
                ),
            ),
        ),
    ]

    for response, expected in responses_and_expected:
        assert response.status_code == 200
        assert response.json() == json.loads(expected.model_dump_json())
        assert response.headers["X-Attendance-API-Contract-Version"] == "1.0.0"


def test_administrative_reporting_routes_keep_safe_authorization_and_validation(
    server_dependencies, employee_factory
) -> None:
    _seed_reporting_data(server_dependencies, employee_factory)

    forbidden = _get(
        _app(server_dependencies),
        "/api/v1/attendance/exceptions?start_date=2026-08-14&end_date=2026-08-14",
        token="employee-token",
    )
    invalid = _get(
        _app(server_dependencies),
        "/api/v1/attendance/organization-analysis?start_date=token%3Dsecret&end_date=2026-08-14",
    )

    assert forbidden.status_code == 403
    assert forbidden.json()["code"] == "FORBIDDEN"
    assert invalid.status_code == 400
    assert invalid.json()["code"] == "INVALID_ARGUMENT"
    assert "token=secret" not in invalid.text


def test_current_attendance_excludes_unknown_and_accepts_only_user_facing_filters(
    server_dependencies, employee_factory
) -> None:
    _seed_reporting_data(server_dependencies, employee_factory)
    with server_dependencies.attendance_session_factory() as session:
        session.add_all(
            [
                employee_factory.build(izvajalec_id=3, priimek="Clark"),
                PunchType(punch_type_id=99, punch_type_desc="Unmapped", active=1),
                AttendanceLog(
                    att_id=12,
                    att_user_id=3,
                    att_punch_type_id=99,
                    att_in=datetime(2026, 8, 14, 8, 0),  # noqa: DTZ001
                ),
            ]
        )
        session.commit()

    app = _app(server_dependencies)
    all_current = _get(app, "/api/v1/attendance/current?as_of=2026-08-14T12:00:00")
    office = _get(
        app, "/api/v1/attendance/current?as_of=2026-08-14T12:00:00&status=office"
    )
    unknown = _get(
        app, "/api/v1/attendance/current?as_of=2026-08-14T12:00:00&status=unknown"
    )

    assert all_current.status_code == 200
    assert all(item["status"] != "unknown" for item in all_current.json()["items"])
    assert office.status_code == 200
    assert all(item["status"] == "office" for item in office.json()["items"])
    assert unknown.status_code == 400
    assert unknown.json()["code"] == "INVALID_ARGUMENT"


def test_current_attendance_accepts_a_repeated_status_filter_set(
    server_dependencies, employee_factory
) -> None:
    _seed_reporting_data(server_dependencies, employee_factory)
    with server_dependencies.attendance_session_factory() as session:
        session.add_all(
            [
                PunchType(punch_type_id=1, punch_type_desc="Office", active=1),
                PunchType(punch_type_id=2, punch_type_desc="Remote", active=1),
            ]
        )
        session.query(AttendanceLog).filter_by(att_id=10).update(
            {"att_punch_type_id": 1, "att_out": None}
        )
        session.query(AttendanceLog).filter_by(att_id=11).update(
            {"att_punch_type_id": 2}
        )
        session.commit()

    response = _get(
        _app(server_dependencies),
        "/api/v1/attendance/current?as_of=2026-08-14T12:00:00"
        "&status=office&status=remote&limit=1",
    )

    assert response.status_code == 200
    assert {item["status"] for item in response.json()["items"]} <= {
        "office",
        "remote",
    }
    assert response.json()["next_offset"] == 1

    duplicate = _get(
        _app(server_dependencies),
        "/api/v1/attendance/current?as_of=2026-08-14T12:00:00"
        "&status=office&status=office",
    )

    assert duplicate.status_code == 400
    assert duplicate.json()["code"] == "INVALID_ARGUMENT"


def test_organization_and_exception_reports_use_a_fixed_query_budget(
    server_dependencies, employee_factory, sqlite_engine
) -> None:
    _seed_reporting_data(server_dependencies, employee_factory)
    statements: list[str] = []

    def count_queries(_connection, _cursor, statement, _parameters, _context, _many):
        statements.append(statement)

    event.listen(sqlite_engine, "before_cursor_execute", count_queries)
    try:
        query = OrganizationAttendanceAnalysisQuery(
            start_date=date(2026, 8, 14), end_date=date(2026, 8, 14)
        )
        get_organization_attendance_analysis(
            requester=_admin(),
            session_factory=server_dependencies.attendance_session_factory,
            query=query,
        )
        organization_query_count = len(statements)
        statements.clear()
        get_attendance_exceptions(
            requester=_admin(),
            session_factory=server_dependencies.attendance_session_factory,
            query=AttendanceExceptionsQuery(**query.model_dump()),
        )
        exception_query_count = len(statements)
    finally:
        event.remove(sqlite_engine, "before_cursor_execute", count_queries)

    assert organization_query_count == 3
    assert exception_query_count == 3
