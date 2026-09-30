"""Attendance-event application service and authorization rules."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from decimal import Decimal

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, joinedload, selectinload, sessionmaker

from attendance_crmt.attendance.contracts import (
    AttendanceAnalysisDay,
    AttendanceEventDetail,
    AttendanceEventPage,
    AttendanceEventQuery,
    AttendanceEventSummary,
    AttendanceException,
    AttendanceExceptionKind,
    AttendanceExceptionsPage,
    AttendanceExceptionsQuery,
    CurrentAttendancePage,
    CurrentAttendanceQuery,
    CurrentAttendanceSummary,
    DailyAttendance,
    DailyAttendanceQuery,
    EmployeeAttendanceAnalysis,
    EmployeeAttendanceAnalysisQuery,
    EmployeeAttendanceAnalysisSummary,
    EmployeeAttendanceSummary,
    LiveAttendanceStatus,
    MyAttendanceEventQuery,
    OrganizationAttendanceAnalysis,
    OrganizationAttendanceAnalysisQuery,
    PlannedWorkDay,
    PlannedWorkQuery,
    PlannedWorkResult,
    PunchTypeHours,
)
from attendance_crmt.identity import Requester
from attendance_crmt.models import AttendanceLog, Employee, PlannedWork
from attendance_crmt.security_errors import SecurityFailure

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
        raise SecurityFailure(code="FORBIDDEN")
    return _list_attendance_events_for_employee(
        session_factory=session_factory,
        query=query,
    )


def list_my_attendance_events(
    *,
    requester: Requester,
    session_factory: sessionmaker[Session],
    query: MyAttendanceEventQuery,
) -> AttendanceEventPage:
    """Return the requester-scoped attendance history without a target-ID input."""
    if requester.employee_id is None:
        raise SecurityFailure(code="IDENTITY_UNMAPPED")
    return _list_attendance_events_for_employee(
        session_factory=session_factory,
        query=AttendanceEventQuery(
            employee_id=requester.employee_id,
            start_date=query.start_date,
            end_date=query.end_date,
            limit=query.limit,
            offset=query.offset,
        ),
    )


def _list_attendance_events_for_employee(
    *,
    session_factory: sessionmaker[Session],
    query: AttendanceEventQuery,
) -> AttendanceEventPage:
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
        items=tuple(
            _attendance_event_summary(event) for event in events[: query.limit]
        ),
        limit=query.limit,
        offset=query.offset,
        next_offset=query.offset + query.limit if has_next_page else None,
    )


def get_attendance_event(
    *,
    requester: Requester,
    session_factory: sessionmaker[Session],
    attendance_event_id: int,
) -> AttendanceEventDetail:
    """Return one administrator-authorized attendance event with audit metadata."""
    if "admin" not in requester.roles:
        raise SecurityFailure(code="FORBIDDEN")
    with session_factory() as session:
        event = session.scalar(
            select(AttendanceLog)
            .options(
                selectinload(AttendanceLog.location),
                selectinload(AttendanceLog.punch_type),
            )
            .where(AttendanceLog.att_id == attendance_event_id)
        )
    if event is None:
        raise LookupError(f"Attendance event {attendance_event_id} was not found.")
    return AttendanceEventDetail(
        **_attendance_event_summary(event).model_dump(),
        edited=event.att_edited == 1,
        recorded_at=event.inserted,
        modified_at=event.modified,
        modified_by=event.user_id,
        data_source=event.data_source,
    )


def get_daily_attendance(
    *,
    requester: Requester,
    session_factory: sessionmaker[Session],
    query: DailyAttendanceQuery,
) -> DailyAttendance:
    """Return raw events and the established daily analysis for one employee."""
    analysis = get_employee_attendance_analysis(
        requester=requester,
        session_factory=session_factory,
        query=EmployeeAttendanceAnalysisQuery(
            employee_id=query.employee_id,
            start_date=query.day,
            end_date=query.day,
        ),
    )
    start_at = datetime.combine(query.day, time.min)
    end_exclusive = start_at + timedelta(days=1)
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
                    AttendanceLog.att_in < end_exclusive,
                    or_(
                        AttendanceLog.att_out.is_(None),
                        AttendanceLog.att_out >= start_at,
                    ),
                )
                .order_by(AttendanceLog.att_in, AttendanceLog.att_id)
            )
        )
    day = analysis.days[0]
    return DailyAttendance(
        employee_id=query.employee_id,
        day=query.day,
        events=[_attendance_event_summary(event) for event in events],
        logged_hours=day.logged_hours,
        known_planned_hours=day.known_planned_hours,
        balance_hours=(
            day.logged_hours - day.known_planned_hours
            if day.known_planned_hours is not None
            else None
        ),
        planned_hours_complete=analysis.planned_hours_complete,
        incomplete_interval_count=day.incomplete_interval_count,
        anomaly_count=day.anomaly_count,
    )


def _attendance_event_summary(event: AttendanceLog) -> AttendanceEventSummary:
    return AttendanceEventSummary(
        attendance_event_id=event.att_id,
        employee_id=event.att_user_id,
        punch_type=event.punch_type.punch_type_desc if event.punch_type else None,
        location=event.location.lokacija_opis if event.location else None,
        checked_in_at=event.att_in,
        checked_out_at=event.att_out,
        note=event.att_opomba,
    )


def get_planned_work(
    *,
    requester: Requester,
    session_factory: sessionmaker[Session],
    query: PlannedWorkQuery,
) -> PlannedWorkResult:
    """Return an administrator-authorized employee planned-work range."""
    if "admin" not in requester.roles:
        raise SecurityFailure(code="FORBIDDEN")
    start_at = datetime.combine(query.start_date, time.min)
    end_exclusive = datetime.combine(query.end_date + timedelta(days=1), time.min)
    with session_factory() as session:
        planned_work = list(
            session.scalars(
                select(PlannedWork)
                .where(
                    PlannedWork.izvajalec_id == query.employee_id,
                    PlannedWork.datum_id >= start_at,
                    PlannedWork.datum_id < end_exclusive,
                )
                .order_by(PlannedWork.datum_id)
            )
        )
    return PlannedWorkResult(
        employee_id=query.employee_id,
        start_date=query.start_date,
        end_date=query.end_date,
        items=[
            PlannedWorkDay(
                day=planned.datum_id.date(), planned_hours=planned.att_planirano_ur_va
            )
            for planned in planned_work
        ],
    )


def list_current_attendance(
    *,
    session_factory: sessionmaker[Session],
    query: CurrentAttendanceQuery,
    include_unknown: bool = True,
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
    if not include_unknown:
        summaries = [summary for summary in summaries if summary.status != "unknown"]
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
        raise SecurityFailure(code="FORBIDDEN")

    return _load_employee_analyses(
        session_factory=session_factory,
        employee_ids=[query.employee_id],
        start_date=query.start_date,
        end_date=query.end_date,
    )[query.employee_id]


def _load_employee_analyses(
    *,
    session_factory: sessionmaker[Session],
    employee_ids: list[int],
    start_date: date,
    end_date: date,
) -> dict[int, EmployeeAttendanceAnalysis]:
    """Load bounded reporting rows in two set-based queries before in-memory analysis."""
    if not employee_ids:
        return {}
    start_at = datetime.combine(start_date, time.min)
    end_exclusive = datetime.combine(end_date + timedelta(days=1), time.min)
    with session_factory() as session:
        events = list(
            session.scalars(
                select(AttendanceLog)
                .options(joinedload(AttendanceLog.punch_type))
                .where(
                    AttendanceLog.att_user_id.in_(employee_ids),
                    AttendanceLog.att_in < end_exclusive,
                    or_(
                        AttendanceLog.att_out.is_(None),
                        AttendanceLog.att_out >= start_at,
                    ),
                )
                .order_by(
                    AttendanceLog.att_user_id,
                    AttendanceLog.att_in,
                    AttendanceLog.att_id,
                )
            )
        )
        planned_work = list(
            session.scalars(
                select(PlannedWork).where(
                    PlannedWork.izvajalec_id.in_(employee_ids),
                    PlannedWork.datum_id >= start_at,
                    PlannedWork.datum_id < end_exclusive,
                )
            )
        )

    events_by_employee: dict[int, list[AttendanceLog]] = {
        employee_id: [] for employee_id in employee_ids
    }
    for event in events:
        events_by_employee[event.att_user_id].append(event)
    planned_by_employee: dict[int, list[PlannedWork]] = {
        employee_id: [] for employee_id in employee_ids
    }
    for planned in planned_work:
        planned_by_employee[planned.izvajalec_id].append(planned)
    return {
        employee_id: _analyze_employee_attendance(
            employee_id=employee_id,
            start_date=start_date,
            end_date=end_date,
            events=events_by_employee[employee_id],
            planned_work=planned_by_employee[employee_id],
        )
        for employee_id in employee_ids
    }


def _analyze_employee_attendance(
    *,
    employee_id: int,
    start_date: date,
    end_date: date,
    events: list[AttendanceLog],
    planned_work: list[PlannedWork],
) -> EmployeeAttendanceAnalysis:
    """Calculate clipped daily totals while excluding incomplete and overlapping intervals."""
    query = EmployeeAttendanceAnalysisQuery(
        employee_id=employee_id, start_date=start_date, end_date=end_date
    )
    start_at = datetime.combine(query.start_date, time.min)
    end_exclusive = datetime.combine(query.end_date + timedelta(days=1), time.min)
    planned_by_day = {
        planned.datum_id.date(): planned.att_planirano_ur_va for planned in planned_work
    }
    daily_logged = {day: Decimal(0) for day in _days_in_range(query)}
    incomplete_by_day = {day: 0 for day in daily_logged}
    anomaly_by_day = {day: 0 for day in daily_logged}
    for event in events:
        if event.att_out is not None:
            continue
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
        employee_id=employee_id,
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
        raise SecurityFailure(code="FORBIDDEN")

    with session_factory() as session:
        employees = list(
            session.scalars(
                select(Employee)
                .where(Employee.active == 1)
                .order_by(Employee.priimek, Employee.ime, Employee.izvajalec_id)
            )
        )

    analyses = _load_employee_analyses(
        session_factory=session_factory,
        employee_ids=[employee.izvajalec_id for employee in employees],
        start_date=query.start_date,
        end_date=query.end_date,
    )
    summaries = [
        _employee_analysis_summary(employee, analyses[employee.izvajalec_id])
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


def get_attendance_exceptions(
    *,
    requester: Requester,
    session_factory: sessionmaker[Session],
    query: AttendanceExceptionsQuery,
) -> AttendanceExceptionsPage:
    """Return a bounded administrator operational report of daily exceptions."""
    if "admin" not in requester.roles:
        raise SecurityFailure(code="FORBIDDEN")
    with session_factory() as session:
        statement = select(Employee).where(Employee.active == 1)
        if query.employee_ids is not None:
            statement = statement.where(Employee.izvajalec_id.in_(query.employee_ids))
        employees = list(session.scalars(statement.order_by(Employee.izvajalec_id)))

    analyses = _load_employee_analyses(
        session_factory=session_factory,
        employee_ids=[employee.izvajalec_id for employee in employees],
        start_date=query.start_date,
        end_date=query.end_date,
    )
    exceptions: list[AttendanceException] = []
    for employee in employees:
        analysis = analyses[employee.izvajalec_id]
        for day in analysis.days:
            if day.missing_attendance:
                exceptions.append(
                    _attendance_exception(employee, day.day, "missing_attendance", 1)
                )
            if day.incomplete_interval_count:
                exceptions.append(
                    _attendance_exception(
                        employee,
                        day.day,
                        "incomplete_interval",
                        day.incomplete_interval_count,
                    )
                )
            if day.anomaly_count:
                exceptions.append(
                    _attendance_exception(
                        employee,
                        day.day,
                        "attendance_anomaly",
                        day.anomaly_count,
                    )
                )
    has_next_page = len(exceptions) > query.offset + query.limit
    return AttendanceExceptionsPage(
        start_date=query.start_date,
        end_date=query.end_date,
        items=exceptions[query.offset : query.offset + query.limit],
        limit=query.limit,
        offset=query.offset,
        next_offset=query.offset + query.limit if has_next_page else None,
    )


def _attendance_exception(
    employee: Employee,
    day: date,
    kind: AttendanceExceptionKind,
    count: int,
) -> AttendanceException:
    return AttendanceException(
        employee_id=employee.izvajalec_id,
        first_name=employee.ime,
        last_name=employee.priimek,
        day=day,
        kind=kind,
        count=count,
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


def get_employee_attendance_summary(
    *,
    requester: Requester,
    session_factory: sessionmaker[Session],
    query: EmployeeAttendanceAnalysisQuery,
) -> EmployeeAttendanceSummary:
    """Return a compact employee summary using the shared analysis semantics."""
    analysis = get_employee_attendance_analysis(
        requester=requester,
        session_factory=session_factory,
        query=query,
    )
    return EmployeeAttendanceSummary(
        employee_id=analysis.employee_id,
        start_date=analysis.start_date,
        end_date=analysis.end_date,
        logged_hours=analysis.logged_hours,
        known_planned_hours=analysis.known_planned_hours,
        balance_hours=analysis.balance_hours,
        planned_hours_complete=analysis.planned_hours_complete,
        punch_type_totals=analysis.punch_type_totals,
        incomplete_interval_count=sum(
            day.incomplete_interval_count for day in analysis.days
        ),
        anomaly_count=sum(day.anomaly_count for day in analysis.days),
    )
