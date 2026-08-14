from datetime import date, datetime
from decimal import Decimal

from attendance_crmt.attendance.contracts import DailyAttendanceQuery
from attendance_crmt.attendance.services import (
    get_attendance_event,
    get_daily_attendance,
)
from attendance_crmt.identity import Requester
from attendance_crmt.models import AttendanceLog, Location, PlannedWork, PunchType

ADMIN = Requester(actor_id="admin", roles=frozenset({"admin"}))


def test_attendance_detail_services_return_one_event_and_daily_totals(
    employee_session_factory,
    employee_factory,
) -> None:
    employee = employee_factory.build(izvajalec_id=42)
    location = Location(lokacija_id=2, lokacija_opis="Company")
    punch_type = PunchType(punch_type_id=1, punch_type_desc="Office", active=1)
    event = AttendanceLog(
        att_id=100,
        att_user_id=employee.izvajalec_id,
        att_location_id=location.lokacija_id,
        att_punch_type_id=punch_type.punch_type_id,
        att_in=datetime(2026, 8, 10, 8, 0),  # noqa: DTZ001
        att_out=datetime(2026, 8, 10, 16, 0),  # noqa: DTZ001
        att_opomba="Customer call",
        att_edited=1,
        inserted=datetime(2026, 8, 10, 16, 1),  # noqa: DTZ001
        modified=datetime(2026, 8, 10, 16, 2),  # noqa: DTZ001
        user_id="admin",
        data_source="MCP",
    )
    with employee_session_factory() as session:
        session.add_all(
            [
                employee,
                location,
                punch_type,
                event,
                PlannedWork(
                    izvajalec_id=employee.izvajalec_id,
                    datum_id=datetime(2026, 8, 10),  # noqa: DTZ001
                    att_planirano_ur_va=Decimal("7.50"),
                ),
            ]
        )
        session.commit()

    detail = get_attendance_event(
        requester=ADMIN,
        session_factory=employee_session_factory,
        attendance_event_id=event.att_id,
    )
    daily = get_daily_attendance(
        requester=ADMIN,
        session_factory=employee_session_factory,
        query=DailyAttendanceQuery(
            employee_id=employee.izvajalec_id, day=date(2026, 8, 10)
        ),
    )

    assert detail.attendance_event_id == event.att_id
    assert detail.employee_id == employee.izvajalec_id
    assert detail.punch_type == "Office"
    assert detail.location == "Company"
    assert detail.edited is True
    assert detail.modified_by == "admin"
    assert daily.logged_hours == Decimal("8.00")
    assert daily.known_planned_hours == Decimal("7.50")
    assert daily.balance_hours == Decimal("0.50")
    assert [item.attendance_event_id for item in daily.events] == [event.att_id]
