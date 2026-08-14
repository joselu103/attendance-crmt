from datetime import date, datetime
from decimal import Decimal

from attendance_crmt.attendance.contracts import EmployeeAttendanceAnalysisQuery
from attendance_crmt.attendance.services import get_employee_attendance_summary
from attendance_crmt.identity import Requester
from attendance_crmt.models import AttendanceLog


def test_employee_summary_omits_daily_detail_from_shared_analysis(
    employee_session_factory,
    employee_factory,
) -> None:
    employee = employee_factory.build(izvajalec_id=45)
    with employee_session_factory() as session:
        session.add_all(
            [
                employee,
                AttendanceLog(
                    att_id=13,
                    att_user_id=employee.izvajalec_id,
                    att_in=datetime(2026, 8, 14, 8, 0),  # noqa: DTZ001
                    att_out=datetime(2026, 8, 14, 16, 0),  # noqa: DTZ001
                ),
            ]
        )
        session.commit()

    result = get_employee_attendance_summary(
        requester=Requester(actor_id="admin", roles=frozenset({"admin"})),
        session_factory=employee_session_factory,
        query=EmployeeAttendanceAnalysisQuery(
            employee_id=employee.izvajalec_id,
            start_date=date(2026, 8, 14),
            end_date=date(2026, 8, 14),
        ),
    )

    assert result.logged_hours == Decimal("8.00")
    assert result.incomplete_interval_count == 0
    assert result.anomaly_count == 0
    assert not hasattr(result, "days")
