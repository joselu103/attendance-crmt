"""Attendance-event application service and authorization rules."""

from __future__ import annotations

from datetime import datetime, time

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload, sessionmaker

from attendance_crmt.attendance.contracts import (
    AttendanceEventPage,
    AttendanceEventQuery,
    AttendanceEventSummary,
)
from attendance_crmt.identity import Requester
from attendance_crmt.models import AttendanceLog


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
