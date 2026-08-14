from datetime import datetime

from attendance_crmt.attendance.contracts import CurrentAttendanceQuery
from attendance_crmt.attendance.services import list_current_attendance
from attendance_crmt.models import AttendanceLog, Location, PunchType


def test_live_attendance_uses_latest_active_interval_per_employee(
    employee_session_factory,
    employee_factory,
) -> None:
    employee = employee_factory.build(izvajalec_id=1)
    office = Location(lokacija_id=2, lokacija_opis="Company")
    remote = Location(lokacija_id=3, lokacija_opis="Home")
    office_type = PunchType(punch_type_id=1, punch_type_desc="Office", active=1)
    remote_type = PunchType(punch_type_id=2, punch_type_desc="Remote", active=1)
    with employee_session_factory() as session:
        session.add_all(
            [
                employee,
                office,
                remote,
                office_type,
                remote_type,
                AttendanceLog(
                    att_id=1,
                    att_user_id=employee.izvajalec_id,
                    att_location_id=office.lokacija_id,
                    att_punch_type_id=office_type.punch_type_id,
                    att_in=datetime(2026, 8, 14, 8, 0),  # noqa: DTZ001
                    att_out=None,
                ),
                AttendanceLog(
                    att_id=2,
                    att_user_id=employee.izvajalec_id,
                    att_location_id=remote.lokacija_id,
                    att_punch_type_id=remote_type.punch_type_id,
                    att_in=datetime(2026, 8, 14, 10, 0),  # noqa: DTZ001
                    att_out=None,
                ),
            ]
        )
        session.commit()

    result = list_current_attendance(
        session_factory=employee_session_factory,
        query=CurrentAttendanceQuery(as_of=datetime(2026, 8, 14, 11, 0)),  # noqa: DTZ001
    )

    assert result.items[0].employee_id == employee.izvajalec_id
    assert result.items[0].status == "remote"
    assert result.items[0].attendance_event_id == 2
