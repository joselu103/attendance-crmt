"""FastMCP attendance-event query tool registrations."""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

from fastmcp import Context, FastMCP
from pydantic import ValidationError
from sqlalchemy.orm import Session, sessionmaker

from attendance_crmt.attendance.contracts import (
    AttendanceEventDetail,
    AttendanceEventPage,
    AttendanceEventQuery,
    AttendanceExceptionsPage,
    AttendanceExceptionsQuery,
    CurrentAttendancePage,
    CurrentAttendanceQuery,
    DailyAttendance,
    DailyAttendanceQuery,
    EmployeeAttendanceAnalysis,
    EmployeeAttendanceAnalysisQuery,
    EmployeeAttendanceSummary,
    LiveAttendanceStatus,
    MyAttendanceEventQuery,
    OrganizationAttendanceAnalysis,
    OrganizationAttendanceAnalysisQuery,
    PlannedWorkQuery,
    PlannedWorkResult,
)
from attendance_crmt.attendance.services import (
    get_attendance_event as query_attendance_event,
)
from attendance_crmt.attendance.services import (
    get_attendance_exceptions as query_attendance_exceptions,
)
from attendance_crmt.attendance.services import (
    get_daily_attendance as query_daily_attendance,
)
from attendance_crmt.attendance.services import (
    get_employee_attendance_analysis as query_employee_attendance_analysis,
)
from attendance_crmt.attendance.services import (
    get_employee_attendance_summary as query_employee_attendance_summary,
)
from attendance_crmt.attendance.services import (
    get_organization_attendance_analysis as query_organization_attendance_analysis,
)
from attendance_crmt.attendance.services import (
    get_planned_work as query_planned_work,
)
from attendance_crmt.attendance.services import (
    list_attendance_events as query_attendance_events,
)
from attendance_crmt.attendance.services import list_current_attendance
from attendance_crmt.attendance.services import (
    list_my_attendance_events as query_my_attendance_events,
)
from attendance_crmt.identity import RequesterResolver
from attendance_crmt.security_errors import SecurityFailure


def _my_attendance_query(
    *,
    start_date: date,
    end_date: date,
    limit: int,
    offset: int,
) -> MyAttendanceEventQuery:
    """Validate requester-supplied criteria without exposing Pydantic diagnostics."""
    try:
        return MyAttendanceEventQuery(
            start_date=start_date,
            end_date=end_date,
            limit=limit,
            offset=offset,
        )
    except ValidationError:
        raise SecurityFailure(code="INVALID_ARGUMENT") from None


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
            "List the requesting employee's attendance events over one through 31 "
            "inclusive calendar days. Employee identity is resolved by the server; "
            "limit must be from 1 through 100 and offset must be nonnegative."
        )
    )
    def list_my_attendance_events(
        start_date: date,
        end_date: date,
        limit: int = 50,
        offset: int = 0,
        ctx: Context | None = None,
    ) -> AttendanceEventPage:
        """Return attendance events scoped to the server-derived requester."""
        return query_my_attendance_events(
            requester=requester_resolver.resolve(ctx),
            session_factory=session_factory,
            query=_my_attendance_query(
                start_date=start_date,
                end_date=end_date,
                limit=limit,
                offset=offset,
            ),
        )

    @server.tool(
        description="Return one attendance event, including recorded audit metadata."
    )
    def get_attendance_event(
        attendance_event_id: int,
        ctx: Context | None = None,
    ) -> AttendanceEventDetail:
        """Return an administrator-authorized attendance-event detail."""
        return query_attendance_event(
            requester=requester_resolver.resolve(ctx),
            session_factory=session_factory,
            attendance_event_id=attendance_event_id,
        )

    @server.tool(
        description=(
            "Return one employee's local-calendar daily attendance events and "
            "calculated planned-versus-logged outcome."
        )
    )
    def get_daily_attendance(
        employee_id: int,
        day: date,
        ctx: Context | None = None,
    ) -> DailyAttendance:
        """Return an administrator-authorized daily attendance view."""
        return query_daily_attendance(
            requester=requester_resolver.resolve(ctx),
            session_factory=session_factory,
            query=DailyAttendanceQuery(employee_id=employee_id, day=day),
        )

    @server.tool(
        description=(
            "Return recorded daily planned-work hours for one employee over an "
            "inclusive Europe/Ljubljana range of up to 31 calendar days."
        )
    )
    def get_planned_work(
        employee_id: int,
        start_date: date,
        end_date: date,
        ctx: Context | None = None,
    ) -> PlannedWorkResult:
        """Return administrator-authorized recorded planned-work rows."""
        return query_planned_work(
            requester=requester_resolver.resolve(ctx),
            session_factory=session_factory,
            query=PlannedWorkQuery(
                employee_id=employee_id,
                start_date=start_date,
                end_date=end_date,
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

    @server.tool(
        description=(
            "Analyze one employee's attendance over an inclusive Europe/Ljubljana "
            "date range of up to 31 calendar days."
        )
    )
    def get_employee_attendance_analysis(
        employee_id: int,
        start_date: date,
        end_date: date,
        ctx: Context | None = None,
    ) -> EmployeeAttendanceAnalysis:
        """Return grouped hours, planned-work comparison, and daily attendance."""
        return query_employee_attendance_analysis(
            requester=requester_resolver.resolve(ctx),
            session_factory=session_factory,
            query=EmployeeAttendanceAnalysisQuery(
                employee_id=employee_id,
                start_date=start_date,
                end_date=end_date,
            ),
        )

    @server.tool(
        description=(
            "Summarize one employee's attendance over an inclusive "
            "Europe/Ljubljana date range of up to 31 calendar days."
        )
    )
    def get_employee_attendance_summary(
        employee_id: int,
        start_date: date,
        end_date: date,
        ctx: Context | None = None,
    ) -> EmployeeAttendanceSummary:
        """Return compact hours and anomaly totals without daily detail."""
        return query_employee_attendance_summary(
            requester=requester_resolver.resolve(ctx),
            session_factory=session_factory,
            query=EmployeeAttendanceAnalysisQuery(
                employee_id=employee_id,
                start_date=start_date,
                end_date=end_date,
            ),
        )

    @server.tool(
        description=(
            "Report missing attendance, incomplete intervals, and invalid or "
            "overlapping interval anomalies over a bounded Europe/Ljubljana range."
        )
    )
    def get_exceptions(
        start_date: date,
        end_date: date,
        employee_ids: list[int] | None = None,
        limit: int = 50,
        offset: int = 0,
        ctx: Context | None = None,
    ) -> AttendanceExceptionsPage:
        """Return an administrator-authorized paginated exception report."""
        return query_attendance_exceptions(
            requester=requester_resolver.resolve(ctx),
            session_factory=session_factory,
            query=AttendanceExceptionsQuery(
                start_date=start_date,
                end_date=end_date,
                employee_ids=employee_ids,
                limit=limit,
                offset=offset,
            ),
        )

    @server.tool(
        description=(
            "Analyze attendance for all active employees over an inclusive "
            "Europe/Ljubljana date range of up to 31 calendar days."
        )
    )
    def get_organization_attendance_analysis(
        start_date: date,
        end_date: date,
        limit: int = 50,
        offset: int = 0,
        ctx: Context | None = None,
    ) -> OrganizationAttendanceAnalysis:
        """Return organization totals and paginated employee analysis summaries."""
        return query_organization_attendance_analysis(
            requester=requester_resolver.resolve(ctx),
            session_factory=session_factory,
            query=OrganizationAttendanceAnalysisQuery(
                start_date=start_date,
                end_date=end_date,
                limit=limit,
                offset=offset,
            ),
        )
