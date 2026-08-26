import asyncio
import json
from dataclasses import replace
from datetime import date, datetime

from fastmcp import Client
from fastmcp.client.client import CallToolResult
from fastmcp.server.auth import AccessToken
from mcp.types import TextContent

from attendance_crmt.identity import AuthenticatedTokenRequesterResolver
from attendance_crmt.models import AttendanceLog
from attendance_crmt.server import create_server


def test_authenticated_requester_sees_only_mapped_employee_attendance(
    server_dependencies,
    employee_factory,
) -> None:
    mapped_employee = employee_factory.build(
        izvajalec_id=42,
        email="person@example.com",
    )
    other_employee = employee_factory.build(
        izvajalec_id=43,
        email="other@example.com",
    )
    with server_dependencies.attendance_session_factory() as session:
        session.add_all(
            [
                mapped_employee,
                other_employee,
                AttendanceLog(
                    att_id=1,
                    att_user_id=mapped_employee.izvajalec_id,
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

    access_token = AccessToken(
        token="validated-test-token",
        client_id="22222222-2222-2222-2222-222222222222",
        scopes=["attendance.access"],
        claims={
            "tid": "11111111-1111-1111-1111-111111111111",
            "oid": "33333333-3333-3333-3333-333333333333",
            "preferred_username": "person@example.com",
            "roles": [],
        },
    )
    resolver = AuthenticatedTokenRequesterResolver(
        session_factory=server_dependencies.attendance_session_factory,
        admin_role="attendance.admin",
        access_token_provider=lambda: access_token,
    )
    server = create_server(replace(server_dependencies, requester_resolver=resolver))

    tools = asyncio.run(server.list_tools())
    my_events_tool = next(
        tool for tool in tools if tool.name == "list_my_attendance_events"
    )
    assert "employee_id" not in my_events_tool.parameters["properties"]
    assert "email" not in my_events_tool.parameters["properties"]
    assert "role" not in my_events_tool.parameters["properties"]

    async def call_tool() -> CallToolResult:
        async with Client(server) as client:
            return await client.call_tool(
                "list_my_attendance_events",
                {
                    "start_date": date(2026, 8, 10),
                    "end_date": date(2026, 8, 10),
                },
                raise_on_error=False,
            )

    result = asyncio.run(call_tool())

    assert result.is_error is False
    assert isinstance(result.content[0], TextContent)
    page = json.loads(result.content[0].text)
    assert [event["employee_id"] for event in page["items"]] == [42]
