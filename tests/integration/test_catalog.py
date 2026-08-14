import asyncio
import json
from datetime import date, datetime

import pytest
from fastmcp.exceptions import ToolError
from sqlalchemy import select

from attendance_crmt.audit import AuditEvent
from attendance_crmt.dependencies import ServerDependencies
from attendance_crmt.identity import (
    Requester,
    StaticRequesterResolver,
)
from attendance_crmt.models import AttendanceLog, Location, PunchType
from attendance_crmt.server import create_server


def test_list_employees_returns_a_bounded_page_of_active_employees(
    employee_session_factory,
    employee_factory,
    audit_log,
) -> None:
    active_employees = employee_factory.build_batch(2)
    inactive_employee = employee_factory.build(active=0)

    with employee_session_factory() as session:
        session.add_all([*active_employees, inactive_employee])
        session.commit()

    server = create_server(
        ServerDependencies(
            attendance_session_factory=employee_session_factory,
            audit_log=audit_log,
        )
    )
    result = asyncio.run(server.call_tool("list_employees", {"limit": 1, "offset": 0}))

    assert result.is_error is False
    page = json.loads(result.content[0].text)
    assert page["limit"] == 1
    assert page["offset"] == 0
    assert page["next_offset"] == 1
    assert len(page["items"]) == 1

    returned_employee = page["items"][0]
    expected_employees = {
        employee.izvajalec_id: employee for employee in active_employees
    }
    expected_employee = expected_employees[returned_employee["employee_id"]]
    assert returned_employee == {
        "employee_id": expected_employee.izvajalec_id,
        "first_name": expected_employee.ime,
        "last_name": expected_employee.priimek,
        "username": expected_employee.username,
        "email": expected_employee.email,
        "active": 1,
    }


def test_audit_middleware_records_a_successful_mcp_tool_interaction(
    employee_session_factory,
    audit_log,
    audit_session_factory,
) -> None:
    server = create_server(
        ServerDependencies(
            attendance_session_factory=employee_session_factory,
            audit_log=audit_log,
        )
    )

    result = asyncio.run(server.call_tool("list_employees", {"limit": 1, "offset": 0}))

    assert result.is_error is False
    with audit_session_factory() as session:
        event = session.scalar(select(AuditEvent))

    assert event is not None
    assert event.tool_name == "list_employees"
    assert event.request_json == '{"limit": 1, "offset": 0}'
    assert event.outcome == "success"


def test_audit_middleware_records_a_failed_mcp_tool_interaction(
    employee_session_factory,
    audit_log,
    audit_session_factory,
) -> None:
    server = create_server(
        ServerDependencies(
            attendance_session_factory=employee_session_factory,
            audit_log=audit_log,
        )
    )

    with pytest.raises(ToolError, match="limit must be between 1 and 100"):
        asyncio.run(server.call_tool("list_employees", {"limit": 0, "offset": 0}))

    with audit_session_factory() as session:
        event = session.scalar(select(AuditEvent))

    assert event is not None
    assert event.tool_name == "list_employees"
    assert event.request_json == '{"limit": 0, "offset": 0}'
    assert event.outcome == "failure"


def test_admin_can_list_an_employees_attendance_events(
    employee_session_factory,
    audit_log,
    audit_session_factory,
    employee_factory,
) -> None:
    employee = employee_factory.build(izvajalec_id=42)
    other_employee = employee_factory.build(izvajalec_id=43)
    location = Location(lokacija_id=3, lokacija_opis="Home")
    punch_type = PunchType(punch_type_id=2, punch_type_desc="Remote work", active=1)
    requested_event = AttendanceLog(
        att_id=100,
        att_user_id=employee.izvajalec_id,
        att_location_id=location.lokacija_id,
        att_punch_type_id=punch_type.punch_type_id,
        att_in=datetime(2026, 8, 10, 8, 0),  # noqa: DTZ001
        att_out=datetime(2026, 8, 10, 16, 0),  # noqa: DTZ001
        att_opomba="Client handover",
    )
    other_event = AttendanceLog(
        att_id=101,
        att_user_id=other_employee.izvajalec_id,
        att_in=datetime(2026, 8, 10, 8, 0),  # noqa: DTZ001
    )
    with employee_session_factory() as session:
        session.add_all(
            [
                employee,
                other_employee,
                location,
                punch_type,
                requested_event,
                other_event,
            ]
        )
        session.commit()

    server = create_server(
        ServerDependencies(
            attendance_session_factory=employee_session_factory,
            audit_log=audit_log,
            requester_resolver=StaticRequesterResolver(
                Requester(actor_id="mvp-admin", roles=frozenset({"admin"}))
            ),
        )
    )

    result = asyncio.run(
        server.call_tool(
            "list_attendance_events",
            {
                "employee_id": employee.izvajalec_id,
                "start_date": date(2026, 8, 10).isoformat(),
                "end_date": date(2026, 8, 10).isoformat(),
            },
        )
    )

    assert result.is_error is False
    assert json.loads(result.content[0].text) == {
        "items": [
            {
                "attendance_event_id": 100,
                "employee_id": 42,
                "punch_type": "Remote work",
                "location": "Home",
                "checked_in_at": "2026-08-10T08:00:00",
                "checked_out_at": "2026-08-10T16:00:00",
                "note": "Client handover",
            }
        ],
        "limit": 50,
        "offset": 0,
        "next_offset": None,
    }
    with audit_session_factory() as session:
        event = session.scalar(select(AuditEvent))

    assert event is not None
    assert event.actor_id == "mvp-admin"


def test_non_admin_cannot_list_an_employees_attendance_events(
    employee_session_factory,
    audit_log,
) -> None:
    server = create_server(
        ServerDependencies(
            attendance_session_factory=employee_session_factory,
            audit_log=audit_log,
            requester_resolver=StaticRequesterResolver(
                Requester(actor_id="mvp-employee", roles=frozenset())
            ),
        )
    )

    with pytest.raises(
        ToolError, match="Only administrators may view another employee's events"
    ):
        asyncio.run(
            server.call_tool(
                "list_attendance_events",
                {
                    "employee_id": 42,
                    "start_date": "2026-08-10",
                    "end_date": "2026-08-10",
                },
            )
        )
