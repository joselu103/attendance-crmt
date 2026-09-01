import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

import httpx
import pytest
from fastmcp import FastMCP
from fastmcp.server.auth import AccessToken, TokenVerifier
from starlette.middleware import Middleware

from attendance_crmt.audit import (
    AuditLog,
    create_audit_engine,
    create_audit_session_factory,
)
from attendance_crmt.audit_middleware import AuditMiddleware
from attendance_crmt.authentication import build_attendance_mcp_middleware
from attendance_crmt.deployment_verification import (
    DeploymentVerificationError,
    EndpointValidationError,
    PublicBoundaryEvidence,
    audit_main,
    build_query,
    main,
    verify_audit_event,
    verify_authenticated_boundary,
    verify_public_boundary,
)
from attendance_crmt.http_contract import (
    ATTENDANCE_MCP_CONTRACT_VERSION,
    CONTRACT_VERSION_HEADER,
)
from attendance_crmt.identity import Requester, StaticRequesterResolver


def test_public_verifier_requires_exact_mcp_https_endpoint() -> None:
    with pytest.raises(EndpointValidationError):
        asyncio.run(verify_public_boundary("https://example.test/mcp/"))

    with pytest.raises(EndpointValidationError):
        asyncio.run(verify_public_boundary("http://example.test/mcp"))


def test_public_verifier_returns_only_safe_authentication_evidence() -> None:
    async def app(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/mcp"
        assert json.loads(request.content) == {}
        return httpx.Response(
            401,
            headers={CONTRACT_VERSION_HEADER: ATTENDANCE_MCP_CONTRACT_VERSION},
            json={"code": "AUTHENTICATION_REQUIRED", "token": "must-not-leak"},
        )

    evidence = asyncio.run(
        verify_public_boundary(
            "https://verification.example/mcp",
            client=httpx.AsyncClient(transport=httpx.MockTransport(app)),
        )
    )

    serialized = json.dumps(evidence.model_dump(mode="json"))
    assert evidence.model_dump() == {
        "endpoint": "https://verification.example/mcp",
        "contract_version": "1.2.0",
        "authentication_status": "authentication_required",
    }
    assert "must-not-leak" not in serialized


@pytest.mark.parametrize("version", ["1", "1.x", "", "2.0.0"])
def test_public_verifier_rejects_malformed_or_incompatible_contract_versions(
    version: str,
) -> None:
    async def app(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            401,
            headers={CONTRACT_VERSION_HEADER: version},
            json={"code": "AUTHENTICATION_REQUIRED"},
        )

    with pytest.raises(DeploymentVerificationError):
        asyncio.run(
            verify_public_boundary(
                "https://verification.example/mcp",
                client=httpx.AsyncClient(transport=httpx.MockTransport(app)),
            )
        )


class StaticTokenVerifier(TokenVerifier):
    async def verify_token(self, token: str) -> AccessToken | None:
        if token != "accepted-test-token":
            return None
        return AccessToken(
            token=token,
            client_id="22222222-2222-2222-2222-222222222222",
            scopes=["attendance.access"],
            subject="test-subject",
            claims={},
        )

    def get_middleware(self) -> list[Middleware]:
        return build_attendance_mcp_middleware(super().get_middleware())


def test_authenticated_verifier_uses_sdk_without_serializing_token_or_events() -> None:
    server = FastMCP(
        "deployment-verifier-test",
        auth=StaticTokenVerifier(base_url="https://verification.example"),
    )

    @server.tool
    def list_my_attendance_events(
        start_date: str, end_date: str, limit: int, offset: int
    ) -> dict[str, object]:
        assert (start_date, end_date, limit, offset) == (
            "2026-08-01",
            "2026-08-31",
            50,
            0,
        )
        return {"items": [{"employee_id": 999, "note": "attendance-event-secret"}]}

    from attendance_crmt.server import create_http_app

    app = create_http_app(server)
    lifespan_app = app
    while hasattr(lifespan_app, "_app"):
        lifespan_app = lifespan_app._app

    async def verify():
        async with lifespan_app.router.lifespan_context(lifespan_app):
            return await verify_authenticated_boundary(
                "https://verification.example/mcp",
                token="accepted-test-token",
                query=build_query("2026-08-01", "2026-08-31"),
                transport=httpx.ASGITransport(app=app),
            )

    evidence = asyncio.run(verify())
    serialized = json.dumps(evidence.model_dump(mode="json"))
    assert evidence.tool_name == "list_my_attendance_events"
    assert "accepted-test-token" not in serialized
    assert "attendance-event-secret" not in serialized
    assert "999" not in serialized


def test_audit_verifier_uses_current_middleware_and_hides_identity_fields(
    tmp_path: Path,
) -> None:
    correlation_id = UUID("11111111-1111-1111-1111-111111111111")
    audit_path = tmp_path / "audit.sqlite3"
    engine = create_audit_engine(audit_path)
    session_factory = create_audit_session_factory(engine)
    middleware = AuditMiddleware(
        AuditLog(session_factory),
        StaticRequesterResolver(
            Requester(
                actor_id="sensitive-actor", employee_id=999, roles=frozenset({"admin"})
            )
        ),
        correlation_id_provider=lambda: correlation_id,
    )
    context = SimpleNamespace(
        message=SimpleNamespace(
            name="list_my_attendance_events",
            arguments={"employee_id": 999, "token": "must-not-leak"},
        )
    )

    class Result:
        is_error = False

    async def call_next(_context: object) -> Result:
        return Result()

    async def record() -> None:
        await middleware.on_call_tool(context, call_next)

    asyncio.run(record())
    evidence = verify_audit_event(
        audit_database_path=audit_path, correlation_id=correlation_id
    )
    serialized = json.dumps(evidence.model_dump(mode="json"))
    assert evidence.model_dump() == {
        "found": True,
        "tool_name": "list_my_attendance_events",
        "outcome": "success",
        "error_code": None,
    }
    assert "sensitive-actor" not in serialized
    assert "999" not in serialized
    assert "must-not-leak" not in serialized
    assert (
        audit_main(
            [
                "--audit-database-path",
                str(audit_path),
                "--correlation-id",
                str(correlation_id),
            ]
        )
        == 0
    )


def test_audit_cli_missing_database_never_creates_parent_or_database(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    audit_path = tmp_path / "missing" / "nested" / "audit.sqlite3"

    assert (
        audit_main(
            [
                "--audit-database-path",
                str(audit_path),
                "--correlation-id",
                "11111111-1111-1111-1111-111111111111",
            ]
        )
        == 1
    )

    captured = capsys.readouterr()
    assert json.loads(captured.err) == {"status": "audit_unavailable"}
    assert captured.out == ""
    assert not audit_path.parent.exists()
    assert not audit_path.exists()


def test_deployment_cli_blocks_missing_token_with_public_evidence_only(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    async def public(*_args: object, **_kwargs: object) -> PublicBoundaryEvidence:
        return PublicBoundaryEvidence(
            endpoint="https://verification.example/mcp",
            contract_version="1.2.0",
            authentication_status="authentication_required",
        )

    monkeypatch.setattr(
        "attendance_crmt.deployment_verification.verify_public_boundary", public
    )
    monkeypatch.delenv("ATTENDANCE_MCP_VERIFICATION_TOKEN", raising=False)

    assert (
        main(
            [
                "--endpoint",
                "https://verification.example/mcp",
                "--start-date",
                "2026-08-01",
                "--end-date",
                "2026-08-31",
            ]
        )
        == 2
    )
    captured = capsys.readouterr()
    assert json.loads(captured.err) == {
        "authenticated_stage": "blocked",
        "public": {
            "authentication_status": "authentication_required",
            "contract_version": "1.2.0",
            "endpoint": "https://verification.example/mcp",
        },
    }
    assert captured.out == ""
