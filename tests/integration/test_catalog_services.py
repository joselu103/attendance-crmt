from attendance_crmt.catalog.contracts import EmployeePage, EmployeePageQuery
from attendance_crmt.catalog.services import list_active_employees


def test_catalog_service_returns_a_transport_independent_page(
    employee_session_factory,
    employee_factory,
) -> None:
    active_employee = employee_factory.build(izvajalec_id=42)
    inactive_employee = employee_factory.build(izvajalec_id=43, active=0)
    with employee_session_factory() as session:
        session.add_all([active_employee, inactive_employee])
        session.commit()

    result = list_active_employees(
        session_factory=employee_session_factory,
        query=EmployeePageQuery(limit=1),
    )

    assert isinstance(result, EmployeePage)
    assert result.items[0].employee_id == active_employee.izvajalec_id
    assert result.next_offset is None
