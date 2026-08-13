import asyncio
import json

import pytest
from fastmcp.exceptions import ToolError
from sqlalchemy import select

from attendance_crmt.audit import AuditEvent
from attendance_crmt.dependencies import ServerDependencies
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
