"""FastMCP catalog and discovery tool registrations."""

from __future__ import annotations

from fastmcp import FastMCP
from pydantic import ValidationError
from sqlalchemy.orm import Session, sessionmaker

from attendance_crmt.catalog.contracts import EmployeePage, EmployeePageQuery
from attendance_crmt.catalog.services import list_active_employees


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


def _validation_message(error: ValidationError) -> str:
    """Expose the shared contract's domain message through the MCP transport."""
    context = error.errors()[0].get("ctx", {})
    cause = context.get("error")
    return str(cause) if cause else str(error)
