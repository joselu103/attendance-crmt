import asyncio
import json
from dataclasses import replace
from datetime import datetime
from typing import Any
from uuid import UUID

import httpx
from fastmcp.server.auth import AccessToken, TokenVerifier
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from sqlalchemy import select
from starlette.middleware import Middleware

from attendance_crmt.audit import AuditEvent
from attendance_crmt.authentication import build_attendance_mcp_middleware
from attendance_crmt.dependencies import ServerDependencies
from attendance_crmt.identity import AuthenticatedTokenRequesterResolver
from attendance_crmt.models import AttendanceLog, Location, PunchType
from attendance_crmt.server import create_http_app, create_server

TENANT_ID = UUID("11111111-1111-1111-1111-111111111111")
OBJECT_ID = UUID("33333333-3333-3333-3333-333333333333")
ACTOR_ID = f"{TENANT_ID}:{OBJECT_ID}"
CORRELATION_ID = "11111111-1111-1111-1111-111111111111"


class StaticTokenVerifier(TokenVerifier):
    async def verify_token(self, token: str) -> AccessToken | None:
        if token != "accepted-test-token":
            return None
        return AccessToken(
            token=token,
            client_id="22222222-2222-2222-2222-222222222222",
            scopes=["attendance.access"],
            subject=ACTOR_ID,
            claims={
                "tid": str(TENANT_ID),
                "oid": str(OBJECT_ID),
                "preferred_username": "person@example.com",
                "roles": [],
            },
        )

    def get_middleware(self) -> list[Middleware]:
        return build_attendance_mcp_middleware(super().get_middleware())


def test_official_sdk_uses_real_attendance_tools_with_requester_authorization(
    server_dependencies: ServerDependencies,
    employee_session_factory,
    employee_factory,
    audit_session_factory,
) -> None:
    employee = employee_factory.build(
        izvajalec_id=42, email="person@example.com", active=1
    )
    other_employee = employee_factory.build(izvajalec_id=43, active=1)
    location = Location(lokacija_id=3, lokacija_opis="Home")
    punch_type = PunchType(punch_type_id=2, punch_type_desc="Remote work", active=1)
    with employee_session_factory() as session:
        session.add_all(
            [
                employee,
                other_employee,
                location,
                punch_type,
                AttendanceLog(
                    att_id=100,
                    att_user_id=42,
                    att_location_id=3,
                    att_punch_type_id=2,
                    att_in=datetime(2026, 8, 10, 8, 0),  # noqa: DTZ001
                    att_out=datetime(2026, 8, 10, 16, 0),  # noqa: DTZ001
                ),
                AttendanceLog(
                    att_id=101,
                    att_user_id=43,
                    att_location_id=3,
                    att_punch_type_id=2,
                    att_in=datetime(2026, 8, 10, 8, 0),  # noqa: DTZ001
                    att_out=datetime(2026, 8, 10, 16, 0),  # noqa: DTZ001
                ),
            ]
        )
        session.commit()

    dependencies = replace(
        server_dependencies,
        auth_provider=StaticTokenVerifier(base_url="http://test"),
        requester_resolver=AuthenticatedTokenRequesterResolver(
            session_factory=employee_session_factory,
            admin_role="attendance.admin",
        ),
    )
    server = create_server(dependencies)
    app = create_http_app(server)

    async def exercise_server() -> tuple[set[str], Any, Any]:
        async with (
            app._app.router.lifespan_context(app._app),
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url="http://test",
                headers={
                    "Authorization": "Bearer accepted-test-token",
                    "X-Correlation-ID": CORRELATION_ID,
                },
            ) as client,
            streamable_http_client("http://test/mcp", http_client=client) as (
                read_stream,
                write_stream,
                _,
            ),
            ClientSession(read_stream, write_stream) as session,
        ):
            await session.initialize()
            tools = await session.list_tools()
            self_result = await session.call_tool(
                "list_my_attendance_events",
                {"start_date": "2026-08-10", "end_date": "2026-08-10"},
            )
            forbidden_result = await session.call_tool(
                "list_attendance_events",
                {
                    "employee_id": 43,
                    "start_date": "2026-08-10",
                    "end_date": "2026-08-10",
                },
            )
            return {tool.name for tool in tools.tools}, self_result, forbidden_result

    tool_names, self_result, forbidden_result = asyncio.run(exercise_server())

    assert {"list_my_attendance_events", "list_attendance_events"} <= tool_names
    assert self_result.isError is False
    self_events = json.loads(self_result.content[0].text)
    assert [event["employee_id"] for event in self_events["items"]] == [42]
    assert forbidden_result.isError is True
    assert json.loads(forbidden_result.content[0].text) == {
        "code": "FORBIDDEN",
        "message": "You do not have permission to do that.",
    }
    with audit_session_factory() as session:
        audit_event = session.scalar(
            select(AuditEvent)
            .where(AuditEvent.tool_name == "list_attendance_events")
            .order_by(AuditEvent.event_id.desc())
        )

    assert audit_event is not None
    assert audit_event.correlation_id == CORRELATION_ID
    assert audit_event.actor_id == ACTOR_ID
    assert audit_event.employee_id == 42
    assert audit_event.roles_json == '["employee"]'
    assert audit_event.outcome == "failure"
    assert audit_event.error_code == "FORBIDDEN"
