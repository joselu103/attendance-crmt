"""Entra token verification and safe MCP authentication transport behavior."""

from collections.abc import MutableMapping
from typing import Any

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from attendance_crmt.security_errors import (
    AUTHENTICATION_REQUIRED_MESSAGE,
    TOKEN_INVALID_MESSAGE,
    SecurityErrorResponse,
)


class AuthenticationErrorContractMiddleware:
    """Replace framework 401 bodies with the stable public security contract."""

    def __init__(self, app: ASGIApp) -> None:
        self._app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        rejected_start: MutableMapping[str, Any] | None = None

        async def send_with_contract(message: Message) -> None:
            nonlocal rejected_start

            if message["type"] == "http.response.start":
                if message["status"] != 401:
                    await send(message)
                    return
                rejected_start = message
                return

            if rejected_start is None:
                await send(message)
                return

            if message["type"] != "http.response.body" or message.get(
                "more_body", False
            ):
                return

            has_authorization = any(
                name.lower() == b"authorization" for name, _ in scope["headers"]
            )
            if has_authorization:
                response = SecurityErrorResponse(
                    code="TOKEN_INVALID",
                    message=TOKEN_INVALID_MESSAGE,
                )
            else:
                response = SecurityErrorResponse(
                    code="AUTHENTICATION_REQUIRED",
                    message=AUTHENTICATION_REQUIRED_MESSAGE,
                )
            body = response.model_dump_json().encode("utf-8")
            authenticate_headers = [
                (name, value)
                for name, value in rejected_start.get("headers", [])
                if name.lower() == b"www-authenticate"
            ]
            await send(
                {
                    "type": "http.response.start",
                    "status": 401,
                    "headers": [
                        *authenticate_headers,
                        (b"content-type", b"application/json"),
                        (b"content-length", str(len(body)).encode("ascii")),
                    ],
                }
            )
            await send({"type": "http.response.body", "body": body})

        await self._app(scope, receive, send_with_contract)
