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
from attendance_crmt.identity import (
    Requester,
    RequesterResolver,
)
from attendance_crmt.observability import (
    bind_identity_context,
    get_logger,
    log_permission_denied,
    reset_identity_context,
)
from attendance_crmt.security_errors import (
    BACKEND_UNAVAILABLE_MESSAGE,
    FORBIDDEN_MESSAGE,
    INTERNAL_ERROR_MESSAGE,
    SecurityErrorCode,
    SecurityErrorResponse,
    SecurityFailure,
)

logger = get_logger(__name__)

_CLIENT_ERROR_CODES = frozenset(
    {
        "AUTHENTICATION_REQUIRED",
        "TOKEN_INVALID",
        "CORRELATION_ID_INVALID",
        "INVALID_ARGUMENT",
        "IDENTITY_UNMAPPED",
        "IDENTITY_AMBIGUOUS",
        "FORBIDDEN",
        "NOT_FOUND",
    }
)


def _duration_ms(started_at: float) -> int:
    """Return a non-negative monotonic duration for lifecycle events."""
    return round((perf_counter() - started_at) * 1000)


def _log_operation_started(*, tool_name: str, correlation_id: UUID) -> None:
    """Emit a safe MCP operation start without retaining tool arguments."""
    logger.info(
        "operation_started",
        correlation_id=str(correlation_id),
        handler=tool_name,
        inputs={},
        state="started",
    )


def _log_operation_step(
    *, tool_name: str, correlation_id: UUID, state: str, started_at: float
) -> None:
    """Emit a safe MCP progress event without retaining tool arguments."""
    logger.info(
        "operation_step",
        correlation_id=str(correlation_id),
        handler=tool_name,
        inputs={},
        state=state,
        duration_ms=_duration_ms(started_at),
    )


def _log_operation_failure(
    *,
    tool_name: str,
    correlation_id: UUID,
    error_code: SecurityErrorCode | None,
    started_at: float,
) -> None:
    """Emit one safe terminal MCP failure event."""
    log = (
        logger.warning
        if error_code in _CLIENT_ERROR_CODES or error_code is None
        else logger.error
    )
    log(
        "operation_failed",
        correlation_id=str(correlation_id),
        handler=tool_name,
        inputs={},
        state="failure",
        error_code=error_code,
        duration_ms=_duration_ms(started_at),
    )


def _classify_public_failure(error: Exception) -> tuple[str | None, Exception]:
    if isinstance(error, SecurityFailure):
        return error.code, error.as_tool_error()
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
        try:
            correlation_id = self._correlation_id_provider()
        except RuntimeError:
            correlation_id = uuid4()
        _log_operation_started(tool_name=tool_name, correlation_id=correlation_id)
        try:
            requester = self._requester_resolver.resolve(context)
        except SecurityFailure as error:
            _log_operation_step(
                tool_name=tool_name,
                correlation_id=correlation_id,
                state="failure_classified",
                started_at=started_at,
            )
            try:
                await self._record_or_raise(
                    tool_name=tool_name,
                    requester=Requester(
                        actor_id=error.actor_id or "unresolved",
                        employee_id=None,
                        roles=frozenset(),
                    ),
                    correlation_id=correlation_id,
                    request=request,
                    outcome="failure",
                    error_code=error.code,
                    started_at=started_at,
                )
            except ToolError:
                _log_operation_failure(
                    tool_name=tool_name,
                    correlation_id=correlation_id,
                    error_code="BACKEND_UNAVAILABLE",
                    started_at=started_at,
                )
                raise
            _log_operation_failure(
                tool_name=tool_name,
                correlation_id=correlation_id,
                error_code=error.code,
                started_at=started_at,
            )
            raise error.as_tool_error() from None

        context_tokens = bind_identity_context(
            subject=requester.actor_id, client_id=requester.client_id
        )
        try:
            try:
                result = await call_next(context)
            except Exception as error:  # noqa: BLE001
                error_code, public_error = _classify_public_failure(error)
                if error_code == "FORBIDDEN":
                    log_permission_denied(
                        subject=requester.actor_id, client_id=requester.client_id
                    )
                _log_operation_step(
                    tool_name=tool_name,
                    correlation_id=correlation_id,
                    state="failure_classified",
                    started_at=started_at,
                )
                try:
                    await self._record_or_raise(
                        tool_name=tool_name,
                        requester=requester,
                        correlation_id=correlation_id,
                        request=request,
                        outcome="failure",
                        error_code=error_code,
                        started_at=started_at,
                    )
                except ToolError:
                    _log_operation_failure(
                        tool_name=tool_name,
                        correlation_id=correlation_id,
                        error_code="BACKEND_UNAVAILABLE",
                        started_at=started_at,
                    )
                    raise
                _log_operation_failure(
                    tool_name=tool_name,
                    correlation_id=correlation_id,
                    error_code=error_code,
                    started_at=started_at,
                )
                raise public_error from None

            outcome = "failure" if getattr(result, "is_error", False) else "success"
            _log_operation_step(
                tool_name=tool_name,
                correlation_id=correlation_id,
                state="tool_completed",
                started_at=started_at,
            )
            try:
                await self._record_or_raise(
                    tool_name=tool_name,
                    requester=requester,
                    correlation_id=correlation_id,
                    request=request,
                    outcome=outcome,
                    error_code=None,
                    started_at=started_at,
                )
            except ToolError:
                _log_operation_failure(
                    tool_name=tool_name,
                    correlation_id=correlation_id,
                    error_code="BACKEND_UNAVAILABLE",
                    started_at=started_at,
                )
                raise
            if outcome == "failure":
                _log_operation_failure(
                    tool_name=tool_name,
                    correlation_id=correlation_id,
                    error_code=None,
                    started_at=started_at,
                )
            else:
                logger.info(
                    "operation_succeeded",
                    correlation_id=str(correlation_id),
                    handler=tool_name,
                    inputs={},
                    state="success",
                    duration_ms=_duration_ms(started_at),
                )
            return result
        finally:
            reset_identity_context(context_tokens)

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
        except Exception:  # noqa: BLE001
            logger.error(
                "mcp_audit_persistence_failed",
                tool_name=tool_name,
                outcome=outcome,
            )
            response = SecurityErrorResponse(
                code="BACKEND_UNAVAILABLE",
                message=BACKEND_UNAVAILABLE_MESSAGE,
            )
            raise ToolError(response.model_dump_json()) from None

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
