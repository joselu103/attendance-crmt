"""HTTP-only MCP contract behavior shared by authenticated server composition."""

from __future__ import annotations

from contextvars import ContextVar
from uuid import UUID

from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from attendance_crmt.security_errors import (
    CORRELATION_ID_INVALID_MESSAGE,
    SecurityErrorResponse,
)

ATTENDANCE_MCP_CONTRACT_VERSION = "1.2.0"
CONTRACT_VERSION_HEADER = "X-Attendance-MCP-Contract-Version"
CORRELATION_ID_HEADER = "X-Correlation-ID"
MCP_PATH = "/mcp"

_current_correlation_id: ContextVar[UUID | None] = ContextVar(
    "attendance_correlation_id",
    default=None,
)


def get_current_correlation_id() -> UUID:
    """Return the validated correlation ID for the active HTTP request."""
    correlation_id = _current_correlation_id.get()
    if correlation_id is None:
        raise RuntimeError("No validated correlation ID is available.")
    return correlation_id


class ContractVersionHeaderMiddleware:
    """Publish the Attendance MCP contract version on MCP HTTP responses."""

    def __init__(self, app: ASGIApp) -> None:
        self._app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["path"] != MCP_PATH:
            await self._app(scope, receive, send)
            return

        async def send_with_contract_version(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers[CONTRACT_VERSION_HEADER] = ATTENDANCE_MCP_CONTRACT_VERSION
            await send(message)

        await self._app(scope, receive, send_with_contract_version)


class CorrelationIdMiddleware:
    """Require one UUID correlation ID after bearer authentication succeeds."""

    def __init__(self, app: ASGIApp) -> None:
        self._app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["path"] != MCP_PATH:
            await self._app(scope, receive, send)
            return

        user = scope.get("user")
        if user is None or not user.is_authenticated:
            await self._app(scope, receive, send)
            return

        correlation_id = _parse_correlation_id(Headers(scope=scope))
        if correlation_id is None:
            await _send_invalid_correlation_response(send)
            return

        token = _current_correlation_id.set(correlation_id)
        try:
            await self._app(scope, receive, send)
        finally:
            _current_correlation_id.reset(token)


def _parse_correlation_id(headers: Headers) -> UUID | None:
    values = headers.getlist(CORRELATION_ID_HEADER)
    if len(values) != 1:
        return None
    try:
        return UUID(values[0])
    except ValueError:
        return None


async def _send_invalid_correlation_response(send: Send) -> None:
    response = SecurityErrorResponse(
        code="CORRELATION_ID_INVALID",
        message=CORRELATION_ID_INVALID_MESSAGE,
    )
    body = response.model_dump_json().encode("utf-8")
    await send(
        {
            "type": "http.response.start",
            "status": 400,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode("ascii")),
            ],
        }
    )
    await send({"type": "http.response.body", "body": body})
