"""Attendance-event application service and authorization rules."""

from __future__ import annotations

from datetime import datetime, time

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload, sessionmaker

from attendance_crmt.attendance.contracts import (
    AttendanceEventPage,
    AttendanceEventQuery,
    AttendanceEventSummary,
    CurrentAttendancePage,
    CurrentAttendanceQuery,
    CurrentAttendanceSummary,
    LiveAttendanceStatus,
)
from attendance_crmt.identity import Requester
from attendance_crmt.models import AttendanceLog, Employee

_PUNCH_TYPE_STATUS: dict[int, LiveAttendanceStatus] = {
    1: "office",
    2: "remote",
    3: "customer_site",
    4: "break",
    5: "break",
    **{punch_type_id: "absence" for punch_type_id in range(6, 16)},
}


def list_attendance_events(
    *,
    requester: Requester,
    session_factory: sessionmaker[Session],
    query: AttendanceEventQuery,
) -> AttendanceEventPage:
    """Authorize the requester and return one employee's attendance events."""
    if "admin" not in requester.roles:
        raise PermissionError("Only administrators may view another employee's events.")

    start_at = datetime.combine(query.start_date, time.min)
    end_at = datetime.combine(query.end_date, time.max)
    with session_factory() as session:
        events = list(
            session.scalars(
                select(AttendanceLog)
                .options(
                    selectinload(AttendanceLog.location),
                    selectinload(AttendanceLog.punch_type),
                )
                .where(
                    AttendanceLog.att_user_id == query.employee_id,
                    AttendanceLog.att_in >= start_at,
                    AttendanceLog.att_in <= end_at,
                )
                .order_by(AttendanceLog.att_in, AttendanceLog.att_id)
                .offset(query.offset)
                .limit(query.limit + 1)
            ).all()
        )
    has_next_page = len(events) > query.limit
    return AttendanceEventPage(
        items=[
            AttendanceEventSummary(
                attendance_event_id=event.att_id,
                employee_id=event.att_user_id,
                punch_type=(
                    event.punch_type.punch_type_desc if event.punch_type else None
                ),
                location=event.location.lokacija_opis if event.location else None,
                checked_in_at=event.att_in,
                checked_out_at=event.att_out,
                note=event.att_opomba,
            )
            for event in events[: query.limit]
        ],
        limit=query.limit,
        offset=query.offset,
        next_offset=query.offset + query.limit if has_next_page else None,
    )


def list_current_attendance(
    *,
    session_factory: sessionmaker[Session],
    query: CurrentAttendanceQuery,
) -> CurrentAttendancePage:
    """Return each active employee's effective status at a local timestamp."""
    with session_factory() as session:
        employees = list(
            session.scalars(
                select(Employee)
                .where(Employee.active == 1)
                .order_by(Employee.priimek, Employee.ime, Employee.izvajalec_id)
            )
        )
        active_events = list(
            session.scalars(
                select(AttendanceLog)
                .options(
                    selectinload(AttendanceLog.location),
                    selectinload(AttendanceLog.punch_type),
                )
                .where(
                    AttendanceLog.att_in <= query.as_of,
                    or_(
                        AttendanceLog.att_out.is_(None),
                        AttendanceLog.att_out >= query.as_of,
                    ),
                )
            )
        )

    latest_event_by_employee: dict[int, AttendanceLog] = {}
    for event in active_events:
        if event.att_in is None:
            continue
        latest_event = latest_event_by_employee.get(event.att_user_id)
        if (
            latest_event is None
            or latest_event.att_in is None
            or event.att_in > latest_event.att_in
        ):
            latest_event_by_employee[event.att_user_id] = event

    summaries = [
        _current_attendance_summary(
            employee, latest_event_by_employee.get(employee.izvajalec_id)
        )
        for employee in employees
    ]
    if query.status is not None:
        summaries = [summary for summary in summaries if summary.status == query.status]
    has_next_page = len(summaries) > query.offset + query.limit
    return CurrentAttendancePage(
        items=summaries[query.offset : query.offset + query.limit],
        as_of=query.as_of,
        limit=query.limit,
        offset=query.offset,
        next_offset=query.offset + query.limit if has_next_page else None,
    )


def _current_attendance_summary(
    employee: Employee, event: AttendanceLog | None
) -> CurrentAttendanceSummary:
    if event is None:
        return CurrentAttendanceSummary(
            employee_id=employee.izvajalec_id,
            first_name=employee.ime,
            last_name=employee.priimek,
            status="no_status",
            attendance_event_id=None,
            started_at=None,
            punch_type=None,
            location=None,
        )
    status: LiveAttendanceStatus = (
        _PUNCH_TYPE_STATUS.get(event.att_punch_type_id, "unknown")
        if event.att_punch_type_id is not None
        else "unknown"
    )
    return CurrentAttendanceSummary(
        employee_id=employee.izvajalec_id,
        first_name=employee.ime,
        last_name=employee.priimek,
        status=status,
        attendance_event_id=event.att_id,
        started_at=event.att_in,
        punch_type=event.punch_type.punch_type_desc if event.punch_type else None,
        location=event.location.lokacija_opis if event.location else None,
    )
