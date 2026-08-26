"""FastMCP middleware for durable tool-interaction audit events."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping
from time import perf_counter
from typing import Any
from uuid import UUID, uuid4

from fastmcp.exceptions import ToolError
from fastmcp.server.middleware import Middleware
from sqlalchemy.exc import SQLAlchemyError

from attendance_crmt.audit import AuditLog
from attendance_crmt.http_contract import get_current_correlation_id
from attendance_crmt.identity import Requester, RequesterResolver
from attendance_crmt.observability import get_logger
from attendance_crmt.security_errors import (
    BACKEND_UNAVAILABLE_MESSAGE,
    FORBIDDEN_MESSAGE,
    INTERNAL_ERROR_MESSAGE,
    SecurityErrorResponse,
)

logger = get_logger(__name__)


def _classify_public_failure(error: Exception) -> tuple[str | None, Exception]:
    if isinstance(error, PermissionError):
        response = SecurityErrorResponse(code="FORBIDDEN", message=FORBIDDEN_MESSAGE)
        return "FORBIDDEN", ToolError(response.model_dump_json())
    if isinstance(error, SQLAlchemyError):
        response = SecurityErrorResponse(
            code="BACKEND_UNAVAILABLE", message=BACKEND_UNAVAILABLE_MESSAGE
        )
        return "BACKEND_UNAVAILABLE", ToolError(response.model_dump_json())
    if isinstance(error, ToolError):
        return None, error
    response = SecurityErrorResponse(
        code="INTERNAL_ERROR", message=INTERNAL_ERROR_MESSAGE
    )
    return "INTERNAL_ERROR", ToolError(response.model_dump_json())


class AuditMiddleware(Middleware):
    """Persist and log the outcome of every MCP tool invocation."""

    def __init__(
        self,
        audit_log: AuditLog,
        requester_resolver: RequesterResolver,
        correlation_id_provider: Callable[[], UUID] = get_current_correlation_id,
    ) -> None:
        self._audit_log = audit_log
        self._requester_resolver = requester_resolver
        self._correlation_id_provider = correlation_id_provider

    async def on_call_tool(self, context: Any, call_next: Any) -> Any:
        started_at = perf_counter()
        tool_name = context.message.name
        request = context.message.arguments or {}
        requester = self._requester_resolver.resolve(context)
        try:
            correlation_id = self._correlation_id_provider()
        except RuntimeError:
            correlation_id = uuid4()

        try:
            result = await call_next(context)
        except Exception as error:
            logger.exception(
                "mcp_tool_interaction",
                tool_name=tool_name,
                outcome="failure",
            )
            error_code, public_error = _classify_public_failure(error)
            await self._record_or_raise(
                tool_name=tool_name,
                requester=requester,
                correlation_id=correlation_id,
                request=request,
                outcome="failure",
                error_code=error_code,
                started_at=started_at,
            )
            raise public_error from None

        outcome = "failure" if getattr(result, "is_error", False) else "success"
        duration_ms = await self._record_or_raise(
            tool_name=tool_name,
            requester=requester,
            correlation_id=correlation_id,
            request=request,
            outcome=outcome,
            error_code=None,
            started_at=started_at,
        )
        logger.info(
            "mcp_tool_interaction",
            tool_name=tool_name,
            outcome=outcome,
            duration_ms=duration_ms,
        )
        return result

    async def _record_or_raise(
        self,
        *,
        tool_name: str,
        requester: Requester,
        correlation_id: UUID,
        request: Mapping[str, Any],
        outcome: str,
        error_code: str | None,
        started_at: float,
    ) -> int:
        try:
            return await self._record(
                tool_name,
                requester,
                correlation_id,
                request,
                outcome,
                error_code,
                started_at,
            )
        except Exception:
            logger.exception(
                "mcp_audit_persistence_failed",
                tool_name=tool_name,
                outcome=outcome,
            )
            raise ToolError(
                "The request could not be completed because audit recording is unavailable."
            ) from None

    async def _record(
        self,
        tool_name: str,
        requester: Requester,
        correlation_id: UUID,
        request: Mapping[str, Any],
        outcome: str,
        error_code: str | None,
        started_at: float,
    ) -> int:
        duration_ms = round((perf_counter() - started_at) * 1000)
        await asyncio.to_thread(
            self._audit_log.record,
            actor_id=requester.actor_id,
            employee_id=requester.employee_id,
            roles=requester.roles,
            correlation_id=correlation_id,
            tool_name=tool_name,
            request=request,
            outcome=outcome,
            error_code=error_code,
            duration_ms=duration_ms,
        )
        return duration_ms
