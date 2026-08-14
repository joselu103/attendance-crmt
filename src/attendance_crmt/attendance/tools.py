"""FastMCP attendance-event query tool registrations."""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

from fastmcp import Context, FastMCP
from sqlalchemy.orm import Session, sessionmaker

from attendance_crmt.attendance.contracts import (
    AttendanceEventPage,
    AttendanceEventQuery,
    CurrentAttendancePage,
    CurrentAttendanceQuery,
    LiveAttendanceStatus,
)
from attendance_crmt.attendance.services import (
    list_attendance_events as query_attendance_events,
)
from attendance_crmt.attendance.services import list_current_attendance
from attendance_crmt.identity import RequesterResolver


def register_attendance_tools(
    server: FastMCP,
    session_factory: sessionmaker[Session],
    requester_resolver: RequesterResolver,
) -> None:
    """Register read-only attendance queries."""

    @server.tool(
        description=(
            "List one employee's attendance events in a bounded date range. "
            "This MVP tool is available only to the server-configured admin requester."
        )
    )
    def list_attendance_events(
        employee_id: int,
        start_date: date,
        end_date: date,
        limit: int = 50,
        offset: int = 0,
        ctx: Context | None = None,
    ) -> AttendanceEventPage:
        """Return attendance events after server-side authorization."""
        return query_attendance_events(
            requester=requester_resolver.resolve(ctx),
            session_factory=session_factory,
            query=AttendanceEventQuery(
                employee_id=employee_id,
                start_date=start_date,
                end_date=end_date,
                limit=limit,
                offset=offset,
            ),
        )

    @server.tool(
        description=(
            "List active employees' effective attendance status at a Europe/Ljubljana "
            "timestamp. Defaults to the current time and supports status filtering."
        )
    )
    def get_current_attendance(
        as_of: datetime | None = None,
        status: LiveAttendanceStatus | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> CurrentAttendancePage:
        """Return paginated active employee presence through the attendance service."""
        local_as_of = as_of or datetime.now(ZoneInfo("Europe/Ljubljana")).replace(
            tzinfo=None
        )
        return list_current_attendance(
            session_factory=session_factory,
            query=CurrentAttendanceQuery(
                as_of=local_as_of,
                status=status,
                limit=limit,
                offset=offset,
            ),
        )
