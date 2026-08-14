from datetime import date, datetime

from attendance_crmt.attendance.contracts import (
    AttendanceEventPage,
    AttendanceEventQuery,
)
from attendance_crmt.attendance.services import list_attendance_events
from attendance_crmt.identity import Requester
from attendance_crmt.models import AttendanceLog, Location, PunchType


def test_attendance_service_returns_a_transport_independent_page(
    employee_session_factory,
    employee_factory,
) -> None:
    employee = employee_factory.build(izvajalec_id=42)
    location = Location(lokacija_id=3, lokacija_opis="Home")
    punch_type = PunchType(punch_type_id=2, punch_type_desc="Remote work", active=1)
    event = AttendanceLog(
        att_id=100,
        att_user_id=employee.izvajalec_id,
        att_location_id=location.lokacija_id,
        att_punch_type_id=punch_type.punch_type_id,
        att_in=datetime(2026, 8, 10, 8, 0),  # noqa: DTZ001
        att_out=datetime(2026, 8, 10, 16, 0),  # noqa: DTZ001
    )
    with employee_session_factory() as session:
        session.add_all([employee, location, punch_type, event])
        session.commit()

    result = list_attendance_events(
        requester=Requester(actor_id="admin", roles=frozenset({"admin"})),
        session_factory=employee_session_factory,
        query=AttendanceEventQuery(
            employee_id=employee.izvajalec_id,
            start_date=date(2026, 8, 10),
            end_date=date(2026, 8, 10),
        ),
    )

    assert isinstance(result, AttendanceEventPage)
    assert result.items[0].attendance_event_id == event.att_id
    assert result.items[0].punch_type == "Remote work"
    assert result.items[0].location == "Home"
