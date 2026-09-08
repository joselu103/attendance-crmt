"""Private REST session-admission behavior for the standalone MCP adapter."""

import asyncio
from dataclasses import replace

import httpx
from fastmcp.server.auth import AccessToken

from attendance_crmt.audit import AuditEvent
from attendance_crmt.identity import AuthenticatedTokenRequesterResolver
from attendance_crmt.rest import create_app

ROUTE = "/internal/v1/mcp/session-admissions"
CORRELATION_ID = "11111111-1111-1111-1111-111111111111"


class StaticTokenVerifier:
    """Verify the delegated bearer CRMT receives from the MCP adapter."""

    async def verify_token(self, token: str) -> AccessToken | None:
        if token != "delegated-token":
            return None
        return AccessToken(
            token=token,
            client_id="22222222-2222-2222-2222-222222222222",
            scopes=["attendance.access"],
            claims={
                "tid": "33333333-3333-3333-3333-333333333333",
                "oid": "44444444-4444-4444-4444-444444444444",
                "preferred_username": "person@example.com",
                "roles": [],
            },
        )


def _post(app, *, headers: list[tuple[str, str]]) -> httpx.Response:
    async def request() -> httpx.Response:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://test",
        ) as client:
            return await client.post(ROUTE, headers=headers)

    return asyncio.run(request())


def _app(server_dependencies):
    resolver = AuthenticatedTokenRequesterResolver(
        session_factory=server_dependencies.attendance_session_factory,
        admin_role="attendance.admin",
    )
    return create_app(
        replace(
            server_dependencies,
            auth_provider=StaticTokenVerifier(),  # type: ignore[arg-type]
            principal_resolver=resolver,
            requester_resolver=resolver,
        )
    )


def test_adapter_can_admit_an_mcp_session_without_receiving_principal_data(
    server_dependencies, employee_factory, audit_session_factory
) -> None:
    employee = employee_factory.build(izvajalec_id=42, email="person@example.com")
    with server_dependencies.attendance_session_factory() as session:
        session.add(employee)
        session.commit()

    response = _post(
        _app(server_dependencies),
        headers=[
            ("Authorization", "Bearer delegated-token"),
            ("X-Correlation-ID", CORRELATION_ID),
        ],
    )

    assert response.status_code == 204
    assert response.content == b""
    assert response.headers["X-Attendance-API-Contract-Version"] == "1.0.0"
    with audit_session_factory() as session:
        event = session.query(AuditEvent).one()
    assert event.correlation_id == CORRELATION_ID
    assert event.tool_name == f"rest:{ROUTE}"
    assert event.outcome == "success"
    assert event.request_json == "{}"


def test_session_admission_keeps_credential_and_correlation_error_precedence(
    server_dependencies, employee_factory, audit_session_factory
) -> None:
    employee = employee_factory.build(izvajalec_id=42, email="person@example.com")
    with server_dependencies.attendance_session_factory() as session:
        session.add(employee)
        session.commit()

    app = _app(server_dependencies)
    missing_bearer = _post(app, headers=[("X-Correlation-ID", "not-a-uuid")])
    invalid_bearer = _post(
        app,
        headers=[
            ("Authorization", "Bearer rejected-token"),
            ("X-Correlation-ID", "not-a-uuid"),
        ],
    )
    invalid_correlation = _post(
        app,
        headers=[("Authorization", "Bearer delegated-token")],
    )

    assert missing_bearer.status_code == 401
    assert missing_bearer.json() == {
        "code": "AUTHENTICATION_REQUIRED",
        "message": "Please sign in to use Attendance.",
    }
    assert invalid_bearer.status_code == 401
    assert invalid_bearer.json() == {
        "code": "TOKEN_INVALID",
        "message": "Your sign-in could not be verified. Please try again.",
    }
    assert invalid_correlation.status_code == 400
    assert invalid_correlation.json() == {
        "code": "CORRELATION_ID_INVALID",
        "message": "The request correlation ID is missing or invalid.",
    }
    for response in (missing_bearer, invalid_bearer, invalid_correlation):
        assert response.headers["X-Attendance-API-Contract-Version"] == "1.0.0"
        assert "delegated-token" not in response.text
        assert "person@example.com" not in response.text
    with audit_session_factory() as session:
        assert session.query(AuditEvent).count() == 0
