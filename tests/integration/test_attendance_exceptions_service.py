from datetime import date, datetime
from decimal import Decimal

from attendance_crmt.attendance.contracts import AttendanceExceptionsQuery
from attendance_crmt.attendance.services import get_attendance_exceptions
from attendance_crmt.identity import Requester
from attendance_crmt.models import AttendanceLog, PlannedWork


def test_attendance_exceptions_reports_missing_incomplete_and_anomalous_days(
    employee_session_factory,
    employee_factory,
) -> None:
    missing_employee = employee_factory.build(izvajalec_id=1)
    incomplete_employee = employee_factory.build(izvajalec_id=2)
    anomalous_employee = employee_factory.build(izvajalec_id=3)
    with employee_session_factory() as session:
        session.add_all(
            [
                missing_employee,
                incomplete_employee,
                anomalous_employee,
                PlannedWork(
                    izvajalec_id=missing_employee.izvajalec_id,
                    datum_id=datetime(2026, 8, 10),  # noqa: DTZ001
                    att_planirano_ur_va=Decimal("8.00"),
                ),
                PlannedWork(
                    izvajalec_id=incomplete_employee.izvajalec_id,
                    datum_id=datetime(2026, 8, 10),  # noqa: DTZ001
                    att_planirano_ur_va=Decimal("8.00"),
                ),
                AttendanceLog(
                    att_id=10,
                    att_user_id=incomplete_employee.izvajalec_id,
                    att_in=datetime(2026, 8, 10, 8, 0),  # noqa: DTZ001
                ),
                AttendanceLog(
                    att_id=20,
                    att_user_id=anomalous_employee.izvajalec_id,
                    att_in=datetime(2026, 8, 10, 8, 0),  # noqa: DTZ001
                    att_out=datetime(2026, 8, 10, 12, 0),  # noqa: DTZ001
                ),
                AttendanceLog(
                    att_id=21,
                    att_user_id=anomalous_employee.izvajalec_id,
                    att_in=datetime(2026, 8, 10, 10, 0),  # noqa: DTZ001
                    att_out=datetime(2026, 8, 10, 14, 0),  # noqa: DTZ001
                ),
            ]
        )
        session.commit()

    result = get_attendance_exceptions(
        requester=Requester(actor_id="admin", roles=frozenset({"admin"})),
        session_factory=employee_session_factory,
        query=AttendanceExceptionsQuery(
            start_date=date(2026, 8, 10),
            end_date=date(2026, 8, 10),
            limit=2,
        ),
    )

    assert [(item.employee_id, item.kind, item.count) for item in result.items] == [
        (1, "missing_attendance", 1),
        (2, "incomplete_interval", 1),
    ]
    assert result.next_offset == 2
