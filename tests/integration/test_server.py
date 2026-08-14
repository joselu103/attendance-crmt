import asyncio
import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from attendance_crmt.models import AttendanceLog, Location, PunchType
from attendance_crmt.server import create_server


def test_create_server_registers_catalog_tools(server_dependencies) -> None:
    server = create_server(server_dependencies)

    tools = asyncio.run(server.list_tools())

    assert server.name == "attendance-crmt"
    assert [tool.name for tool in tools] == [
        "list_employees",
        "list_attendance_events",
        "get_current_attendance",
    ]


def test_current_attendance_serializes_naive_timestamps_as_rfc_3339(
    server_dependencies,
    employee_factory,
) -> None:
    employee = employee_factory.build(izvajalec_id=1)
    location = Location(lokacija_id=2, lokacija_opis="Company")
    punch_type = PunchType(punch_type_id=1, punch_type_desc="Office", active=1)
    local_as_of = datetime.now(ZoneInfo("Europe/Ljubljana")).replace(tzinfo=None)
    with server_dependencies.attendance_session_factory() as session:
        session.add_all(
            [
                employee,
                location,
                punch_type,
                AttendanceLog(
                    att_id=1,
                    att_user_id=employee.izvajalec_id,
                    att_location_id=location.lokacija_id,
                    att_punch_type_id=punch_type.punch_type_id,
                    att_in=local_as_of - timedelta(hours=1),
                    att_out=None,
                ),
            ]
        )
        session.commit()

    server = create_server(server_dependencies)

    result = asyncio.run(server.call_tool("get_current_attendance", {"as_of": None}))

    assert result.is_error is False
    page = json.loads(result.content[0].text)
    assert datetime.fromisoformat(page["as_of"]).tzinfo is not None
    assert datetime.fromisoformat(page["items"][0]["started_at"]).tzinfo is not None
