import asyncio
from typing import Any

import httpx
from fastmcp import FastMCP
from fastmcp.server.auth import AccessToken, TokenVerifier
from starlette.middleware import Middleware

from attendance_crmt.authentication import build_attendance_mcp_middleware
from attendance_crmt.http_contract import (
    ATTENDANCE_MCP_CONTRACT_VERSION,
    CONTRACT_VERSION_HEADER,
    CORRELATION_ID_HEADER,
    get_current_correlation_id,
)
from attendance_crmt.security_errors import (
    AUTHENTICATION_REQUIRED_MESSAGE,
    CORRELATION_ID_INVALID_MESSAGE,
    TOKEN_INVALID_MESSAGE,
)


class StaticTokenVerifier(TokenVerifier):
    async def verify_token(self, token: str) -> AccessToken | None:
        if token != "accepted-test-token":
            return None
        return AccessToken(
            token=token,
            client_id="22222222-2222-2222-2222-222222222222",
            scopes=["attendance.access"],
            subject="11111111-1111-1111-1111-111111111111:33333333-3333-3333-3333-333333333333",
            claims={},
        )

    def get_middleware(self) -> list[Middleware]:
        return build_attendance_mcp_middleware(super().get_middleware())


def _mcp_app():
    server = FastMCP(
        "http-contract-test", auth=StaticTokenVerifier(base_url="http://test")
    )

    @server.tool
    def current_correlation_id() -> str:
        return str(get_current_correlation_id())

    return server.http_app(path="/mcp", stateless_http=True, json_response=True)


def _post_mcp(
    app: Any,
    headers: list[tuple[str, str]] | None = None,
    body: dict[str, Any] | None = None,
) -> httpx.Response:
    async def request() -> httpx.Response:
        async with (
            app.router.lifespan_context(app),
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url="http://test",
            ) as client,
        ):
            return await client.post(
                "/mcp",
                headers=[
                    ("Accept", "application/json, text/event-stream"),
                    *(headers or []),
                ],
                json=body or {},
            )

    return asyncio.run(request())


def _assert_contract_version(response: httpx.Response) -> None:
    assert response.headers[CONTRACT_VERSION_HEADER] == ATTENDANCE_MCP_CONTRACT_VERSION


def test_missing_bearer_keeps_authentication_required_precedence() -> None:
    response = _post_mcp(_mcp_app())

    assert response.status_code == 401
    assert response.json() == {
        "code": "AUTHENTICATION_REQUIRED",
        "message": AUTHENTICATION_REQUIRED_MESSAGE,
    }
    _assert_contract_version(response)


def test_invalid_bearer_keeps_token_invalid_precedence() -> None:
    response = _post_mcp(
        _mcp_app(),
        headers=[("Authorization", "Bearer rejected-test-token")],
    )

    assert response.status_code == 401
    assert response.json() == {
        "code": "TOKEN_INVALID",
        "message": TOKEN_INVALID_MESSAGE,
    }
    _assert_contract_version(response)


def test_authenticated_request_requires_correlation_id() -> None:
    response = _post_mcp(
        _mcp_app(),
        headers=[("Authorization", "Bearer accepted-test-token")],
    )

    assert response.status_code == 400
    assert response.json() == {
        "code": "CORRELATION_ID_INVALID",
        "message": CORRELATION_ID_INVALID_MESSAGE,
    }
    _assert_contract_version(response)


def test_authenticated_request_rejects_malformed_correlation_id() -> None:
    response = _post_mcp(
        _mcp_app(),
        headers=[
            ("Authorization", "Bearer accepted-test-token"),
            (CORRELATION_ID_HEADER, "not-a-uuid"),
        ],
    )

    assert response.status_code == 400
    assert response.json() == {
        "code": "CORRELATION_ID_INVALID",
        "message": CORRELATION_ID_INVALID_MESSAGE,
    }
    _assert_contract_version(response)


def test_authenticated_request_rejects_duplicate_correlation_ids() -> None:
    response = _post_mcp(
        _mcp_app(),
        headers=[
            ("Authorization", "Bearer accepted-test-token"),
            (CORRELATION_ID_HEADER, "11111111-1111-1111-1111-111111111111"),
            (CORRELATION_ID_HEADER, "22222222-2222-2222-2222-222222222222"),
        ],
    )

    assert response.status_code == 400
    assert response.json() == {
        "code": "CORRELATION_ID_INVALID",
        "message": CORRELATION_ID_INVALID_MESSAGE,
    }
    _assert_contract_version(response)


def test_authenticated_request_propagates_normalized_correlation_id_to_tool() -> None:
    response = _post_mcp(
        _mcp_app(),
        headers=[
            ("Authorization", "Bearer accepted-test-token"),
            (CORRELATION_ID_HEADER, "11111111111111111111111111111111"),
        ],
        body={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "current_correlation_id", "arguments": {}},
        },
    )

    assert response.status_code == 200
    assert response.json()["result"]["content"] == [
        {
            "type": "text",
            "text": "11111111-1111-1111-1111-111111111111",
        }
    ]
    _assert_contract_version(response)
