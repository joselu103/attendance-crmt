"""FastMCP middleware for durable tool-interaction audit events."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from time import perf_counter
from typing import Any

from fastmcp.exceptions import ToolError
from fastmcp.server.middleware import Middleware

from attendance_crmt.audit import AuditLog
from attendance_crmt.observability import get_logger

logger = get_logger(__name__)


class AuditMiddleware(Middleware):
    """Persist and log the outcome of every MCP tool invocation."""

    def __init__(self, audit_log: AuditLog) -> None:
        self._audit_log = audit_log

    async def on_call_tool(self, context: Any, call_next: Any) -> Any:
        started_at = perf_counter()
        tool_name = context.message.name
        request = context.message.arguments or {}

        try:
            result = await call_next(context)
        except Exception:
            logger.exception(
                "mcp_tool_interaction",
                tool_name=tool_name,
                outcome="failure",
            )
            await self._record_or_raise(
                tool_name=tool_name,
                request=request,
                outcome="failure",
                started_at=started_at,
            )
            raise

        outcome = "failure" if getattr(result, "is_error", False) else "success"
        duration_ms = await self._record_or_raise(
            tool_name=tool_name,
            request=request,
            outcome=outcome,
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
        request: Mapping[str, Any],
        outcome: str,
        started_at: float,
    ) -> int:
        try:
            return await self._record(tool_name, request, outcome, started_at)
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
        request: Mapping[str, Any],
        outcome: str,
        started_at: float,
    ) -> int:
        duration_ms = round((perf_counter() - started_at) * 1000)
        await asyncio.to_thread(
            self._audit_log.record,
            tool_name=tool_name,
            request=request,
            outcome=outcome,
            duration_ms=duration_ms,
        )
        return duration_ms
