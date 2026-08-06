"""Catalog and discovery tool registrations."""

from __future__ import annotations

from dataclasses import dataclass

from fastmcp import FastMCP
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from attendance_crmt.database import (
    create_engine_from_environment,
    create_session_factory,
)
from attendance_crmt.models import Employee


@dataclass(frozen=True)
class EmployeeSummary:
    """A directory-safe employee representation for catalog lookups."""

    employee_id: int
    first_name: str
    last_name: str
    username: str
    email: str | None
    active: int | None


@dataclass(frozen=True)
class EmployeePage:
    """A bounded page of employee directory results."""

    items: list[EmployeeSummary]
    limit: int
    offset: int
    next_offset: int | None


def register_catalog_tools(
    server: FastMCP, session_factory: sessionmaker[Session] | None = None
) -> None:
    """Register read-only catalog tools.

    A supplied session factory keeps database access testable. Production session
    creation remains lazy so importing and composing the MCP server needs no
    database configuration.
    """

    def get_session_factory() -> sessionmaker[Session]:
        nonlocal session_factory

        if session_factory is None:
            session_factory = create_session_factory(create_engine_from_environment())
        return session_factory

    @server.tool(
        description=(
            "List active employees for attendance lookups. Inactive employee "
            "records are excluded. Results use bounded limit/offset pagination."
        )
    )
    def list_employees(limit: int = 50, offset: int = 0) -> EmployeePage:
        """Return a page of active employees ordered by surname and given name.

        ``limit`` must be between 1 and 100, inclusive. ``offset`` is zero-based.

        Future endpoint-level authentication can be enforced by passing an
        ``auth=...`` check to ``server.tool`` once an HTTP authentication provider
        and caller-to-employee mapping have been defined.
        """
        if not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100.")
        if offset < 0:
            raise ValueError("offset must not be negative.")

        with get_session_factory()() as session:
            employees = session.scalars(
                select(Employee)
                .where(Employee.active == 1)
                .order_by(Employee.priimek, Employee.ime, Employee.izvajalec_id)
                .offset(offset)
                .limit(limit + 1)
            ).all()

        has_next_page = len(employees) > limit
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
                for employee in employees[:limit]
            ],
            limit=limit,
            offset=offset,
            next_offset=offset + limit if has_next_page else None,
        )
