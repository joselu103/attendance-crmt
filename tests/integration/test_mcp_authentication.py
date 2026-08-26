import asyncio

import httpx
from fastmcp import FastMCP
from fastmcp.server.auth import TokenVerifier
from starlette.middleware import Middleware

from attendance_crmt.authentication import AuthenticationErrorContractMiddleware


class RejectAllTokenVerifier(TokenVerifier):
    async def verify_token(self, token: str):
        return None

    def get_middleware(self) -> list[Middleware]:
        return [
            Middleware(AuthenticationErrorContractMiddleware),
            *super().get_middleware(),
        ]


def _post_mcp(app, *, authorization: str | None = None) -> httpx.Response:
    async def request() -> httpx.Response:
        headers = {"Authorization": authorization} if authorization else {}
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            return await client.post("/mcp", headers=headers, json={})

    return asyncio.run(request())


def test_missing_token_returns_authentication_required() -> None:
    verifier = RejectAllTokenVerifier(base_url="http://test")
    server = FastMCP("authentication-test", auth=verifier)
    app = server.http_app(path="/mcp", stateless_http=True)

    response = _post_mcp(app)

    assert response.status_code == 401
    assert response.json() == {
        "code": "AUTHENTICATION_REQUIRED",
        "message": "Please sign in to use Attendance.",
    }
