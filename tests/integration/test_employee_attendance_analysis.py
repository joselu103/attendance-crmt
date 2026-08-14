from datetime import date, datetime
from decimal import Decimal

from attendance_crmt.attendance.contracts import EmployeeAttendanceAnalysisQuery
from attendance_crmt.attendance.services import get_employee_attendance_analysis
from attendance_crmt.identity import Requester
from attendance_crmt.models import AttendanceLog, PlannedWork, PunchType


def test_employee_analysis_groups_completed_intervals_and_compares_planned_hours(
    employee_session_factory,
    employee_factory,
) -> None:
    employee = employee_factory.build(izvajalec_id=42)
    office_type = PunchType(punch_type_id=1, punch_type_desc="Office", active=1)
    break_type = PunchType(punch_type_id=4, punch_type_desc="Lunch", active=1)
    with employee_session_factory() as session:
        session.add_all(
            [
                employee,
                office_type,
                break_type,
                PlannedWork(
                    izvajalec_id=employee.izvajalec_id,
                    datum_id=datetime(2026, 8, 10),  # noqa: DTZ001
                    att_planirano_ur_va=Decimal("8.00"),
                ),
                PlannedWork(
                    izvajalec_id=employee.izvajalec_id,
                    datum_id=datetime(2026, 8, 11),  # noqa: DTZ001
                    att_planirano_ur_va=Decimal("8.00"),
                ),
                AttendanceLog(
                    att_id=1,
                    att_user_id=employee.izvajalec_id,
                    att_punch_type_id=office_type.punch_type_id,
                    att_in=datetime(2026, 8, 10, 8, 0),  # noqa: DTZ001
                    att_out=datetime(2026, 8, 10, 16, 0),  # noqa: DTZ001
                ),
                AttendanceLog(
                    att_id=2,
                    att_user_id=employee.izvajalec_id,
                    att_punch_type_id=break_type.punch_type_id,
                    att_in=datetime(2026, 8, 11, 12, 0),  # noqa: DTZ001
                    att_out=datetime(2026, 8, 11, 13, 0),  # noqa: DTZ001
                ),
            ]
        )
        session.commit()

    result = get_employee_attendance_analysis(
        requester=Requester(actor_id="admin", roles=frozenset({"admin"})),
        session_factory=employee_session_factory,
        query=EmployeeAttendanceAnalysisQuery(
            employee_id=employee.izvajalec_id,
            start_date=date(2026, 8, 10),
            end_date=date(2026, 8, 11),
        ),
    )

    assert result.logged_hours == Decimal("9.00")
    assert result.known_planned_hours == Decimal("16.00")
    assert result.balance_hours == Decimal("-7.00")
    assert [
        (total.punch_type_id, total.hours) for total in result.punch_type_totals
    ] == [
        (1, Decimal("8.00")),
        (4, Decimal("1.00")),
    ]
    assert [day.logged_hours for day in result.days] == [
        Decimal("8.00"),
        Decimal("1.00"),
    ]


def test_employee_analysis_marks_open_interval_as_incomplete_not_missing_attendance(
    employee_session_factory,
    employee_factory,
) -> None:
    employee = employee_factory.build(izvajalec_id=43)
    with employee_session_factory() as session:
        session.add_all(
            [
                employee,
                PlannedWork(
                    izvajalec_id=employee.izvajalec_id,
                    datum_id=datetime(2026, 8, 12),  # noqa: DTZ001
                    att_planirano_ur_va=Decimal("8.00"),
                ),
                AttendanceLog(
                    att_id=3,
                    att_user_id=employee.izvajalec_id,
                    att_in=datetime(2026, 8, 12, 8, 0),  # noqa: DTZ001
                    att_out=None,
                ),
            ]
        )
        session.commit()

    result = get_employee_attendance_analysis(
        requester=Requester(actor_id="admin", roles=frozenset({"admin"})),
        session_factory=employee_session_factory,
        query=EmployeeAttendanceAnalysisQuery(
            employee_id=employee.izvajalec_id,
            start_date=date(2026, 8, 12),
            end_date=date(2026, 8, 12),
        ),
    )

    assert result.days[0].incomplete_interval_count == 1
    assert result.days[0].missing_attendance is False


def test_employee_analysis_excludes_overlapping_completed_intervals_as_anomalies(
    employee_session_factory,
    employee_factory,
) -> None:
    employee = employee_factory.build(izvajalec_id=44)
    with employee_session_factory() as session:
        session.add_all(
            [
                employee,
                AttendanceLog(
                    att_id=4,
                    att_user_id=employee.izvajalec_id,
                    att_in=datetime(2026, 8, 13, 8, 0),  # noqa: DTZ001
                    att_out=datetime(2026, 8, 13, 12, 0),  # noqa: DTZ001
                ),
                AttendanceLog(
                    att_id=5,
                    att_user_id=employee.izvajalec_id,
                    att_in=datetime(2026, 8, 13, 10, 0),  # noqa: DTZ001
                    att_out=datetime(2026, 8, 13, 14, 0),  # noqa: DTZ001
                ),
            ]
        )
        session.commit()

    result = get_employee_attendance_analysis(
        requester=Requester(actor_id="admin", roles=frozenset({"admin"})),
        session_factory=employee_session_factory,
        query=EmployeeAttendanceAnalysisQuery(
            employee_id=employee.izvajalec_id,
            start_date=date(2026, 8, 13),
            end_date=date(2026, 8, 13),
        ),
    )

    assert result.logged_hours == Decimal(0)
    assert result.days[0].anomaly_count == 2
