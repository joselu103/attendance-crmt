"""Regression coverage for yearly compact attendance reports."""

from datetime import date, datetime
from decimal import Decimal

from attendance_crmt.attendance.contracts import AnnualAttendanceSummaryQuery
from attendance_crmt.attendance.services import (
    get_employee_annual_attendance_summary,
    get_my_annual_attendance_summary,
)
from attendance_crmt.identity import Requester
from attendance_crmt.models import AttendanceLog


def test_yearly_summaries_allow_366_days_for_self_and_administrator(
    employee_session_factory, employee_factory
) -> None:
    employee = employee_factory.build(izvajalec_id=45)
    with employee_session_factory() as session:
        session.add_all(
            [
                employee,
                AttendanceLog(
                    att_id=13,
                    att_user_id=45,
                    att_in=datetime(2024, 1, 1, 8, 0),  # noqa: DTZ001
                    att_out=datetime(2024, 1, 1, 16, 0),  # noqa: DTZ001
                ),
            ]
        )
        session.commit()

    query = AnnualAttendanceSummaryQuery(
        employee_id=45, start_date=date(2024, 1, 1), end_date=date(2024, 12, 31)
    )
    admin_result = get_employee_annual_attendance_summary(
        requester=Requester(actor_id="admin", roles=frozenset({"admin"})),
        session_factory=employee_session_factory,
        query=query,
    )
    self_result = get_my_annual_attendance_summary(
        requester=Requester(
            actor_id="employee", employee_id=45, roles=frozenset({"employee"})
        ),
        session_factory=employee_session_factory,
        start_date=query.start_date,
        end_date=query.end_date,
    )

    assert admin_result.logged_hours == Decimal("8.00")
    assert self_result == admin_result
