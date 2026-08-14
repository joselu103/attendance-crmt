from datetime import date, datetime
from decimal import Decimal

from attendance_crmt.attendance.contracts import OrganizationAttendanceAnalysisQuery
from attendance_crmt.attendance.services import get_organization_attendance_analysis
from attendance_crmt.identity import Requester
from attendance_crmt.models import AttendanceLog, PlannedWork


def test_organization_analysis_totals_all_active_employees_before_pagination(
    employee_session_factory,
    employee_factory,
) -> None:
    first_employee = employee_factory.build(izvajalec_id=1, priimek="Adams")
    second_employee = employee_factory.build(izvajalec_id=2, priimek="Baker")
    inactive_employee = employee_factory.build(izvajalec_id=3, active=0)
    with employee_session_factory() as session:
        session.add_all(
            [
                first_employee,
                second_employee,
                inactive_employee,
                PlannedWork(
                    izvajalec_id=first_employee.izvajalec_id,
                    datum_id=datetime(2026, 8, 14),  # noqa: DTZ001
                    att_planirano_ur_va=Decimal("8.00"),
                ),
                PlannedWork(
                    izvajalec_id=second_employee.izvajalec_id,
                    datum_id=datetime(2026, 8, 14),  # noqa: DTZ001
                    att_planirano_ur_va=Decimal("8.00"),
                ),
                AttendanceLog(
                    att_id=10,
                    att_user_id=first_employee.izvajalec_id,
                    att_in=datetime(2026, 8, 14, 8, 0),  # noqa: DTZ001
                    att_out=datetime(2026, 8, 14, 16, 0),  # noqa: DTZ001
                ),
                AttendanceLog(
                    att_id=11,
                    att_user_id=second_employee.izvajalec_id,
                    att_in=datetime(2026, 8, 14, 8, 0),  # noqa: DTZ001
                    att_out=datetime(2026, 8, 14, 14, 0),  # noqa: DTZ001
                ),
                AttendanceLog(
                    att_id=12,
                    att_user_id=inactive_employee.izvajalec_id,
                    att_in=datetime(2026, 8, 14, 8, 0),  # noqa: DTZ001
                    att_out=datetime(2026, 8, 14, 18, 0),  # noqa: DTZ001
                ),
            ]
        )
        session.commit()

    result = get_organization_attendance_analysis(
        requester=Requester(actor_id="admin", roles=frozenset({"admin"})),
        session_factory=employee_session_factory,
        query=OrganizationAttendanceAnalysisQuery(
            start_date=date(2026, 8, 14),
            end_date=date(2026, 8, 14),
            limit=1,
        ),
    )

    assert result.active_employee_count == 2
    assert result.logged_hours == Decimal("14.00")
    assert result.known_planned_hours == Decimal("16.00")
    assert result.balance_hours == Decimal("-2.00")
    assert [summary.employee_id for summary in result.items] == [
        first_employee.izvajalec_id
    ]
    assert result.next_offset == 1
