"""FastMCP catalog and discovery tool registrations."""

from __future__ import annotations

from fastmcp import FastMCP
from pydantic import ValidationError
from sqlalchemy.orm import Session, sessionmaker

from attendance_crmt.catalog.contracts import (
    EmployeePage,
    EmployeePageQuery,
    EmployeeSummary,
    LocationSummary,
    PunchTypeSummary,
)
from attendance_crmt.catalog.services import (
    get_employee as query_employee,
)
from attendance_crmt.catalog.services import (
    list_active_employees,
)
from attendance_crmt.catalog.services import (
    list_locations as query_locations,
)
from attendance_crmt.catalog.services import (
    list_punch_types as query_punch_types,
)


def register_catalog_tools(
    server: FastMCP, session_factory: sessionmaker[Session]
) -> None:
    """Register read-only catalog tools with their application session factory."""

    @server.tool(
        description=(
            "List active employees for attendance lookups. Inactive employee "
            "records are excluded. Results use bounded limit/offset pagination."
        )
    )
    def list_employees(limit: int = 50, offset: int = 0) -> EmployeePage:
        """Return a page of active employees through the catalog service."""
        try:
            query = EmployeePageQuery(limit=limit, offset=offset)
        except ValidationError as error:
            raise ValueError(_validation_message(error)) from None
        return list_active_employees(
            session_factory=session_factory,
            query=query,
        )

    @server.tool(description="Return one employee's directory-safe metadata by ID.")
    def get_employee(employee_id: int) -> EmployeeSummary:
        """Resolve one employee through the catalog service."""
        return query_employee(
            session_factory=session_factory,
            employee_id=employee_id,
        )

    @server.tool(
        description=(
            "List configured punch types and their server-derived attendance locations. "
            "Locations are reference data, not caller-selected input."
        )
    )
    def list_punch_types(active_only: bool = True) -> list[PunchTypeSummary]:
        """Return configured punch-type reference data."""
        return query_punch_types(
            session_factory=session_factory,
            active_only=active_only,
        )

    @server.tool(description="List attendance-event location reference data.")
    def list_locations() -> list[LocationSummary]:
        """Return location reference data."""
        return query_locations(session_factory=session_factory)


def _validation_message(error: ValidationError) -> str:
    """Expose the shared contract's domain message through the MCP transport."""
    context = error.errors()[0].get("ctx", {})
    cause = context.get("error")
    return str(cause) if cause else str(error)
