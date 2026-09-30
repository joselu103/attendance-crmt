"""Employee discovery application services."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from attendance_crmt.catalog.contracts import (
    EmployeePage,
    EmployeePageQuery,
    EmployeeResolveQuery,
    EmployeeSummary,
    LocationSummary,
    PunchTypeSummary,
)
from attendance_crmt.identity import Requester
from attendance_crmt.models import Employee, Location, PunchType
from attendance_crmt.security_errors import SecurityFailure

_PUNCH_TYPE_LOCATION_IDS = {
    1: 2,
    2: 3,
    3: 1,
    4: 5,
    5: 5,
    6: 4,
    7: 5,
    8: 5,
    9: 5,
    10: 4,
    11: 4,
    12: 5,
    13: 5,
    14: 5,
    15: 5,
}


def list_active_employees(
    *,
    session_factory: sessionmaker[Session],
    query: EmployeePageQuery,
) -> EmployeePage:
    """Return active employees ordered by surname and given name."""
    with session_factory() as session:
        employees = session.scalars(
            select(Employee)
            .where(Employee.active == 1)
            .order_by(Employee.priimek, Employee.ime, Employee.izvajalec_id)
            .offset(query.offset)
            .limit(query.limit + 1)
        ).all()

    has_next_page = len(employees) > query.limit
    return EmployeePage(
        items=[
            EmployeeSummary(
                employee_id=employee.izvajalec_id,
                first_name=employee.ime,
                last_name=employee.priimek,
                username=employee.username,
                email=employee.email,
                active=employee.active,
            )
            for employee in employees[: query.limit]
        ],
        limit=query.limit,
        offset=query.offset,
        next_offset=query.offset + query.limit if has_next_page else None,
    )


def get_employee(
    *, session_factory: sessionmaker[Session], employee_id: int
) -> EmployeeSummary:
    """Return one employee's directory-safe metadata."""
    with session_factory() as session:
        employee = session.get(Employee, employee_id)
    if employee is None:
        raise LookupError(f"Employee {employee_id} was not found.")
    return _employee_summary(employee)


def resolve_employee(
    *,
    requester: Requester,
    session_factory: sessionmaker[Session],
    query: EmployeeResolveQuery,
) -> EmployeeSummary:
    """Resolve exactly one directory-safe employee record for an administrator."""
    if "admin" not in requester.roles:
        raise SecurityFailure(code="FORBIDDEN")

    statement = select(Employee)
    if query.employee_id is not None:
        statement = statement.where(Employee.izvajalec_id == query.employee_id)
    elif query.username is not None:
        statement = statement.where(Employee.username == query.username)
    else:
        statement = statement.where(Employee.email == query.email)
    with session_factory() as session:
        employees = list(session.scalars(statement))
    employees = [
        employee
        for employee in employees
        if (
            employee.izvajalec_id == query.employee_id
            if query.employee_id is not None
            else employee.username == query.username
            if query.username is not None
            else employee.email == query.email
        )
    ]
    if len(employees) != 1:
        raise LookupError("Employee was not found.")
    return _employee_summary(employees[0])


def list_punch_types(
    *, session_factory: sessionmaker[Session], active_only: bool = True
) -> list[PunchTypeSummary]:
    """Return configured punch types with their confirmed derived locations."""
    with session_factory() as session:
        punch_type_statement = select(PunchType).order_by(PunchType.punch_type_id)
        if active_only:
            punch_type_statement = punch_type_statement.where(PunchType.active == 1)
        punch_types = list(session.scalars(punch_type_statement))
        locations_by_id = {
            location.lokacija_id: location
            for location in session.scalars(select(Location))
        }
    return [
        PunchTypeSummary(
            punch_type_id=punch_type.punch_type_id,
            punch_type=punch_type.punch_type_desc,
            active=punch_type.active,
            derived_location_id=_PUNCH_TYPE_LOCATION_IDS.get(punch_type.punch_type_id),
            derived_location=(
                locations_by_id[location_id].lokacija_opis
                if (
                    location_id := _PUNCH_TYPE_LOCATION_IDS.get(
                        punch_type.punch_type_id
                    )
                )
                in locations_by_id
                else None
            ),
        )
        for punch_type in punch_types
    ]


def list_locations(*, session_factory: sessionmaker[Session]) -> list[LocationSummary]:
    """Return recorded-attendance locations in stable identifier order."""
    with session_factory() as session:
        locations = list(
            session.scalars(select(Location).order_by(Location.lokacija_id))
        )
    return [
        LocationSummary(
            location_id=location.lokacija_id, location=location.lokacija_opis
        )
        for location in locations
    ]


def _employee_summary(employee: Employee) -> EmployeeSummary:
    return EmployeeSummary(
        employee_id=employee.izvajalec_id,
        first_name=employee.ime,
        last_name=employee.priimek,
        username=employee.username,
        email=employee.email,
        active=employee.active,
    )
