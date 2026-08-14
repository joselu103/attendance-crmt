"""Attendance-event application service and authorization rules."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from decimal import Decimal

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload, sessionmaker

from attendance_crmt.attendance.contracts import (
    AttendanceAnalysisDay,
    AttendanceEventPage,
    AttendanceEventQuery,
    AttendanceEventSummary,
    CurrentAttendancePage,
    CurrentAttendanceQuery,
    CurrentAttendanceSummary,
    EmployeeAttendanceAnalysis,
    EmployeeAttendanceAnalysisQuery,
    EmployeeAttendanceAnalysisSummary,
    LiveAttendanceStatus,
    OrganizationAttendanceAnalysis,
    OrganizationAttendanceAnalysisQuery,
    PunchTypeHours,
)
from attendance_crmt.identity import Requester
from attendance_crmt.models import AttendanceLog, Employee, PlannedWork

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


def get_employee_attendance_analysis(
    *,
    requester: Requester,
    session_factory: sessionmaker[Session],
    query: EmployeeAttendanceAnalysisQuery,
) -> EmployeeAttendanceAnalysis:
    """Return an administrator-authorized daily and grouped attendance analysis."""
    if "admin" not in requester.roles:
        raise PermissionError(
            "Only administrators may view another employee's analysis."
        )

    start_at = datetime.combine(query.start_date, time.min)
    end_exclusive = datetime.combine(query.end_date + timedelta(days=1), time.min)
    with session_factory() as session:
        events = list(
            session.scalars(
                select(AttendanceLog)
                .options(selectinload(AttendanceLog.punch_type))
                .where(
                    AttendanceLog.att_user_id == query.employee_id,
                    AttendanceLog.att_in < end_exclusive,
                    AttendanceLog.att_out >= start_at,
                )
                .order_by(AttendanceLog.att_in, AttendanceLog.att_id)
            )
        )
        incomplete_events = list(
            session.scalars(
                select(AttendanceLog).where(
                    AttendanceLog.att_user_id == query.employee_id,
                    AttendanceLog.att_in < end_exclusive,
                    AttendanceLog.att_out.is_(None),
                )
            )
        )
        planned_work = list(
            session.scalars(
                select(PlannedWork).where(
                    PlannedWork.izvajalec_id == query.employee_id,
                    PlannedWork.datum_id >= start_at,
                    PlannedWork.datum_id < end_exclusive,
                )
            )
        )

    planned_by_day = {
        planned.datum_id.date(): planned.att_planirano_ur_va for planned in planned_work
    }
    daily_logged = {day: Decimal(0) for day in _days_in_range(query)}
    incomplete_by_day = {day: 0 for day in daily_logged}
    anomaly_by_day = {day: 0 for day in daily_logged}
    for event in incomplete_events:
        if event.att_in is not None:
            incomplete_day = max(event.att_in, start_at).date()
            if incomplete_day in incomplete_by_day:
                incomplete_by_day[incomplete_day] += 1

    valid_events: list[AttendanceLog] = []
    anomalous_event_ids: set[int] = set()
    for event in events:
        if (
            event.att_in is None
            or event.att_out is None
            or event.att_out <= event.att_in
        ):
            anomalous_event_ids.add(event.att_id)
        else:
            valid_events.append(event)
    for event_index, event in enumerate(valid_events):
        for subsequent_event in valid_events[event_index + 1 :]:
            if (
                event.att_out is not None
                and subsequent_event.att_in is not None
                and subsequent_event.att_in < event.att_out
            ):
                anomalous_event_ids.update((event.att_id, subsequent_event.att_id))

    punch_totals: dict[tuple[int | None, str | None], Decimal] = {}
    for event in valid_events:
        if event.att_in is None or event.att_out is None:
            continue
        if event.att_id in anomalous_event_ids:
            if event.att_in is not None:
                anomaly_day = max(event.att_in, start_at).date()
                if anomaly_day in anomaly_by_day:
                    anomaly_by_day[anomaly_day] += 1
            continue
        clipped_start = max(event.att_in, start_at)
        clipped_end = min(event.att_out, end_exclusive)
        hours = _interval_hours(clipped_start, clipped_end)
        key = (
            event.att_punch_type_id,
            event.punch_type.punch_type_desc if event.punch_type else None,
        )
        punch_totals[key] = punch_totals.get(key, Decimal(0)) + hours
        for day, day_hours in _daily_hours(clipped_start, clipped_end):
            daily_logged[day] += day_hours

    known_planned_hours = sum(
        (value or Decimal(0) for value in planned_by_day.values()), Decimal(0)
    )
    planned_hours_complete = all(day in planned_by_day for day in daily_logged)
    logged_hours = sum(daily_logged.values(), Decimal(0))
    days = [
        AttendanceAnalysisDay(
            day=day,
            known_planned_hours=planned_by_day.get(day),
            logged_hours=daily_logged[day],
            missing_attendance=(planned_by_day.get(day) or Decimal(0)) > 0
            and daily_logged[day] == 0
            and incomplete_by_day[day] == 0,
            incomplete_interval_count=incomplete_by_day[day],
            anomaly_count=anomaly_by_day[day],
        )
        for day in daily_logged
    ]
    return EmployeeAttendanceAnalysis(
        employee_id=query.employee_id,
        start_date=query.start_date,
        end_date=query.end_date,
        logged_hours=logged_hours,
        known_planned_hours=known_planned_hours,
        balance_hours=(logged_hours - known_planned_hours)
        if planned_hours_complete
        else None,
        planned_hours_complete=planned_hours_complete,
        punch_type_totals=[
            PunchTypeHours(punch_type_id=key[0], punch_type=key[1], hours=hours)
            for key, hours in punch_totals.items()
        ],
        days=days,
    )


def _days_in_range(query: EmployeeAttendanceAnalysisQuery) -> list[date]:
    return [
        query.start_date + timedelta(days=offset)
        for offset in range((query.end_date - query.start_date).days + 1)
    ]


def _interval_hours(start: datetime, end: datetime) -> Decimal:
    return Decimal(str((end - start).total_seconds() / 3600))


def _daily_hours(start: datetime, end: datetime) -> list[tuple[date, Decimal]]:
    result: list[tuple[date, Decimal]] = []
    current = start
    while current < end:
        next_midnight = datetime.combine(current.date() + timedelta(days=1), time.min)
        segment_end = min(end, next_midnight)
        result.append((current.date(), _interval_hours(current, segment_end)))
        current = segment_end
    return result


def get_organization_attendance_analysis(
    *,
    requester: Requester,
    session_factory: sessionmaker[Session],
    query: OrganizationAttendanceAnalysisQuery,
) -> OrganizationAttendanceAnalysis:
    """Return active-workforce totals and a page of employee analysis summaries."""
    if "admin" not in requester.roles:
        raise PermissionError("Only administrators may view organization analysis.")

    with session_factory() as session:
        employees = list(
            session.scalars(
                select(Employee)
                .where(Employee.active == 1)
                .order_by(Employee.priimek, Employee.ime, Employee.izvajalec_id)
            )
        )

    summaries = [
        _employee_analysis_summary(
            employee,
            get_employee_attendance_analysis(
                requester=requester,
                session_factory=session_factory,
                query=EmployeeAttendanceAnalysisQuery(
                    employee_id=employee.izvajalec_id,
                    start_date=query.start_date,
                    end_date=query.end_date,
                ),
            ),
        )
        for employee in employees
    ]
    logged_hours = sum((summary.logged_hours for summary in summaries), Decimal(0))
    known_planned_hours = sum(
        (summary.known_planned_hours for summary in summaries), Decimal(0)
    )
    planned_hours_complete = all(
        summary.planned_hours_complete for summary in summaries
    )
    has_next_page = len(summaries) > query.offset + query.limit
    return OrganizationAttendanceAnalysis(
        start_date=query.start_date,
        end_date=query.end_date,
        active_employee_count=len(summaries),
        logged_hours=logged_hours,
        known_planned_hours=known_planned_hours,
        balance_hours=(logged_hours - known_planned_hours)
        if planned_hours_complete
        else None,
        planned_hours_complete=planned_hours_complete,
        items=summaries[query.offset : query.offset + query.limit],
        limit=query.limit,
        offset=query.offset,
        next_offset=query.offset + query.limit if has_next_page else None,
    )


def _employee_analysis_summary(
    employee: Employee, analysis: EmployeeAttendanceAnalysis
) -> EmployeeAttendanceAnalysisSummary:
    return EmployeeAttendanceAnalysisSummary(
        employee_id=employee.izvajalec_id,
        first_name=employee.ime,
        last_name=employee.priimek,
        logged_hours=analysis.logged_hours,
        known_planned_hours=analysis.known_planned_hours,
        balance_hours=analysis.balance_hours,
        planned_hours_complete=analysis.planned_hours_complete,
        incomplete_interval_count=sum(
            day.incomplete_interval_count for day in analysis.days
        ),
        anomaly_count=sum(day.anomaly_count for day in analysis.days),
    )
