import asyncio
import json

from attendance_crmt.server import create_server


def test_list_employees_returns_a_bounded_page_of_active_employees(
    employee_session_factory,
    employee_factory,
) -> None:
    active_employees = employee_factory.build_batch(2)
    inactive_employee = employee_factory.build(active=0)

    with employee_session_factory() as session:
        session.add_all([*active_employees, inactive_employee])
        session.commit()

    server = create_server(session_factory=employee_session_factory)
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
