from datetime import date, datetime

from attendance_crmt.attendance.contracts import MyAttendanceEventQuery
from attendance_crmt.attendance.services import list_my_attendance_events
from attendance_crmt.identity import Requester
from attendance_crmt.models import AttendanceLog


def test_list_my_attendance_events_uses_server_derived_employee_identity(
    employee_session_factory,
    employee_factory,
) -> None:
    requester_employee = employee_factory.build(izvajalec_id=42)
    other_employee = employee_factory.build(izvajalec_id=43)
    with employee_session_factory() as session:
        session.add_all(
            [
                requester_employee,
                other_employee,
                AttendanceLog(
                    att_id=1,
                    att_user_id=requester_employee.izvajalec_id,
                    att_in=datetime(2026, 8, 10, 8, 0),  # noqa: DTZ001
                ),
                AttendanceLog(
                    att_id=2,
                    att_user_id=other_employee.izvajalec_id,
                    att_in=datetime(2026, 8, 10, 8, 0),  # noqa: DTZ001
                ),
            ]
        )
        session.commit()

    result = list_my_attendance_events(
        requester=Requester(
            actor_id="employee-42",
            roles=frozenset(),
            employee_id=requester_employee.izvajalec_id,
        ),
        session_factory=employee_session_factory,
        query=MyAttendanceEventQuery(
            start_date=date(2026, 8, 10),
            end_date=date(2026, 8, 10),
        ),
    )

    assert [event.employee_id for event in result.items] == [
        requester_employee.izvajalec_id
    ]
