from attendance_crmt.catalog.services import (
    get_employee,
    list_locations,
    list_punch_types,
)
from attendance_crmt.models import Location, PunchType


def test_catalog_lookup_services_return_employee_punch_type_and_location_data(
    employee_session_factory,
    employee_factory,
) -> None:
    employee = employee_factory.build(izvajalec_id=42)
    company = Location(lokacija_id=2, lokacija_opis="Company")
    inactive_location = Location(lokacija_id=5, lokacija_opis="Other")
    office = PunchType(punch_type_id=1, punch_type_desc="Office", active=1)
    inactive_type = PunchType(punch_type_id=2, punch_type_desc="Remote", active=0)
    with employee_session_factory() as session:
        session.add_all([employee, company, inactive_location, office, inactive_type])
        session.commit()

    employee_result = get_employee(
        session_factory=employee_session_factory,
        employee_id=employee.izvajalec_id,
    )
    punch_types = list_punch_types(session_factory=employee_session_factory)
    locations = list_locations(session_factory=employee_session_factory)

    assert employee_result.employee_id == employee.izvajalec_id
    assert [(item.punch_type_id, item.derived_location) for item in punch_types] == [
        (office.punch_type_id, "Company")
    ]
    assert [(item.location_id, item.location) for item in locations] == [
        (company.lokacija_id, "Company"),
        (inactive_location.lokacija_id, "Other"),
    ]
