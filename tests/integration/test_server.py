import asyncio
import json
from dataclasses import replace
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from fastmcp import Client
from fastmcp.client.client import CallToolResult
from fastmcp.server.auth import AccessToken
from mcp.types import TextContent

from attendance_crmt.identity import AuthenticatedTokenRequesterResolver
from attendance_crmt.models import AttendanceLog, Location, PunchType
from attendance_crmt.security_errors import IDENTITY_UNMAPPED_MESSAGE
from attendance_crmt.server import create_server


def test_create_server_registers_catalog_tools(server_dependencies) -> None:
    server = create_server(server_dependencies)

    tools = asyncio.run(server.list_tools())

    assert server.name == "attendance-crmt"
    assert [tool.name for tool in tools] == [
        "list_employees",
        "get_employee",
        "list_punch_types",
        "list_locations",
        "list_attendance_events",
        "list_my_attendance_events",
        "get_attendance_event",
        "get_daily_attendance",
        "get_planned_work",
        "get_current_attendance",
        "get_employee_attendance_analysis",
        "get_employee_attendance_summary",
        "get_exceptions",
        "get_organization_attendance_analysis",
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


def test_identity_mapping_error_preserves_stable_mcp_payload(
    server_dependencies,
) -> None:
    access_token = AccessToken(
        token="validated-test-token",
        client_id="22222222-2222-2222-2222-222222222222",
        scopes=["attendance.access"],
        claims={
            "tid": "11111111-1111-1111-1111-111111111111",
            "oid": "33333333-3333-3333-3333-333333333333",
            "preferred_username": "unmapped@example.com",
        },
    )
    resolver = AuthenticatedTokenRequesterResolver(
        session_factory=server_dependencies.attendance_session_factory,
        admin_role="attendance.admin",
        access_token_provider=lambda: access_token,
    )
    dependencies = replace(server_dependencies, requester_resolver=resolver)
    server = create_server(dependencies)

    async def call_tool() -> CallToolResult:
        async with Client(server) as client:
            return await client.call_tool(
                "list_my_attendance_events",
                {
                    "start_date": date(2026, 8, 1),
                    "end_date": date(2026, 8, 2),
                },
                raise_on_error=False,
            )

    result = asyncio.run(call_tool())

    assert result.is_error is True
    assert isinstance(result.content[0], TextContent)
    assert json.loads(result.content[0].text) == {
        "code": "IDENTITY_UNMAPPED",
        "message": IDENTITY_UNMAPPED_MESSAGE,
    }
