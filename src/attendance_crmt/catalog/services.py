"""Employee discovery application services."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from attendance_crmt.catalog.contracts import (
    EmployeePage,
    EmployeePageQuery,
    EmployeeSummary,
)
from attendance_crmt.models import Employee


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
