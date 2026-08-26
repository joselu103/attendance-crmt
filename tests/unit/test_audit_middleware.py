import asyncio
import json
from types import SimpleNamespace
from typing import Any
from uuid import UUID

import pytest
from fastmcp.exceptions import ToolError
from sqlalchemy.exc import OperationalError

from attendance_crmt import audit_middleware
from attendance_crmt.audit_middleware import AuditMiddleware
from attendance_crmt.identity import (
    AuthenticatedIdentityResolutionError,
    Requester,
    StaticRequesterResolver,
)
from attendance_crmt.observability import configure_structlog, get_logger
from attendance_crmt.security_errors import IDENTITY_UNMAPPED_MESSAGE


class CapturingAuditLog:
    def __init__(self) -> None:
        self.records: list[dict[str, Any]] = []

    def record(self, **kwargs: Any) -> None:
        self.records.append(kwargs)


def test_audit_middleware_records_authenticated_request_context() -> None:
    audit_log = CapturingAuditLog()
    correlation_id = UUID("11111111-1111-1111-1111-111111111111")
    middleware = AuditMiddleware(
        audit_log=audit_log,  # type: ignore[arg-type]
        requester_resolver=StaticRequesterResolver(
            Requester(
                actor_id="22222222-2222-2222-2222-222222222222:33333333-3333-3333-3333-333333333333",
                employee_id=42,
                roles=frozenset({"admin", "employee"}),
            )
        ),
        correlation_id_provider=lambda: correlation_id,
    )
    context = SimpleNamespace(
        message=SimpleNamespace(name="future_tool", arguments={"employee_id": 42})
    )

    result = asyncio.run(
        middleware.on_call_tool(
            context,
            lambda _context: _successful_tool_result(),
        )
    )

    assert result.is_error is False
    assert len(audit_log.records) == 1
    record = audit_log.records[0].copy()
    assert record.pop("duration_ms") >= 0
    assert record == {
        "actor_id": "22222222-2222-2222-2222-222222222222:33333333-3333-3333-3333-333333333333",
        "employee_id": 42,
        "roles": frozenset({"admin", "employee"}),
        "correlation_id": correlation_id,
        "tool_name": "future_tool",
        "request": {"employee_id": 42},
        "outcome": "success",
        "error_code": None,
    }


class FailingAuditLog:
    def record(self, **kwargs: Any) -> None:
        raise OSError("audit database unavailable")


def test_audit_middleware_replaces_audit_store_failures_with_safe_error_code() -> None:
    middleware = AuditMiddleware(
        audit_log=FailingAuditLog(),  # type: ignore[arg-type]
        requester_resolver=StaticRequesterResolver(
            Requester(actor_id="actor", employee_id=42, roles=frozenset({"employee"}))
        ),
        correlation_id_provider=lambda: UUID("11111111-1111-1111-1111-111111111111"),
    )
    context = SimpleNamespace(message=SimpleNamespace(name="future_tool", arguments={}))

    with pytest.raises(ToolError, match='"BACKEND_UNAVAILABLE"'):
        asyncio.run(
            middleware.on_call_tool(context, lambda _context: _successful_tool_result())
        )


class FailingIdentityResolver:
    def resolve(self, context: Any) -> Requester:
        raise AuthenticatedIdentityResolutionError(
            code="IDENTITY_UNMAPPED",
            message=IDENTITY_UNMAPPED_MESSAGE,
            actor_id="22222222-2222-2222-2222-222222222222:33333333-3333-3333-3333-333333333333",
        )


def test_audit_middleware_records_partial_identity_context() -> None:
    audit_log = CapturingAuditLog()
    middleware = AuditMiddleware(
        audit_log=audit_log,  # type: ignore[arg-type]
        requester_resolver=FailingIdentityResolver(),  # type: ignore[arg-type]
        correlation_id_provider=lambda: UUID("11111111-1111-1111-1111-111111111111"),
    )
    context = SimpleNamespace(message=SimpleNamespace(name="future_tool", arguments={}))

    with pytest.raises(ToolError, match='"IDENTITY_UNMAPPED"'):
        asyncio.run(
            middleware.on_call_tool(context, lambda _context: _successful_tool_result())
        )

    assert audit_log.records[0]["actor_id"] == (
        "22222222-2222-2222-2222-222222222222:33333333-3333-3333-3333-333333333333"
    )
    assert audit_log.records[0]["employee_id"] is None
    assert audit_log.records[0]["roles"] == frozenset()
    assert audit_log.records[0]["error_code"] == "IDENTITY_UNMAPPED"


async def _successful_tool_result() -> SimpleNamespace:
    return SimpleNamespace(is_error=False)


async def _forbidden_tool_result() -> SimpleNamespace:
    raise PermissionError("backend authorization detail")


def test_audit_middleware_replaces_permission_failures_with_safe_error_code() -> None:
    audit_log = CapturingAuditLog()
    middleware = AuditMiddleware(
        audit_log=audit_log,  # type: ignore[arg-type]
        requester_resolver=StaticRequesterResolver(
            Requester(actor_id="actor", employee_id=42, roles=frozenset({"employee"}))
        ),
        correlation_id_provider=lambda: UUID("11111111-1111-1111-1111-111111111111"),
    )
    context = SimpleNamespace(message=SimpleNamespace(name="future_tool", arguments={}))

    with pytest.raises(ToolError, match='"FORBIDDEN"'):
        asyncio.run(
            middleware.on_call_tool(context, lambda _context: _forbidden_tool_result())
        )

    assert audit_log.records[0]["outcome"] == "failure"
    assert audit_log.records[0]["error_code"] == "FORBIDDEN"


async def _unavailable_tool_result() -> SimpleNamespace:
    raise OperationalError("SELECT 1", {}, ConnectionError("database unavailable"))


def test_audit_middleware_replaces_database_failures_with_safe_error_code() -> None:
    audit_log = CapturingAuditLog()
    middleware = AuditMiddleware(
        audit_log=audit_log,  # type: ignore[arg-type]
        requester_resolver=StaticRequesterResolver(
            Requester(actor_id="actor", employee_id=42, roles=frozenset({"employee"}))
        ),
        correlation_id_provider=lambda: UUID("11111111-1111-1111-1111-111111111111"),
    )
    context = SimpleNamespace(message=SimpleNamespace(name="future_tool", arguments={}))

    with pytest.raises(ToolError, match='"BACKEND_UNAVAILABLE"'):
        asyncio.run(
            middleware.on_call_tool(
                context, lambda _context: _unavailable_tool_result()
            )
        )

    assert audit_log.records[0]["outcome"] == "failure"
    assert audit_log.records[0]["error_code"] == "BACKEND_UNAVAILABLE"


async def _unexpected_tool_result() -> SimpleNamespace:
    raise RuntimeError("database password leaked")


async def _tool_result_with_sensitive_diagnostic() -> SimpleNamespace:
    raise RuntimeError("sensitive diagnostic sentinel")


def test_audit_middleware_replaces_unexpected_failures_with_safe_error_code() -> None:
    audit_log = CapturingAuditLog()
    middleware = AuditMiddleware(
        audit_log=audit_log,  # type: ignore[arg-type]
        requester_resolver=StaticRequesterResolver(
            Requester(actor_id="actor", employee_id=42, roles=frozenset({"employee"}))
        ),
        correlation_id_provider=lambda: UUID("11111111-1111-1111-1111-111111111111"),
    )
    context = SimpleNamespace(message=SimpleNamespace(name="future_tool", arguments={}))

    with pytest.raises(ToolError, match='"INTERNAL_ERROR"'):
        asyncio.run(
            middleware.on_call_tool(context, lambda _context: _unexpected_tool_result())
        )

    assert audit_log.records[0]["outcome"] == "failure"
    assert audit_log.records[0]["error_code"] == "INTERNAL_ERROR"


def test_unexpected_tool_failure_log_omits_exception_details(
    capsys, monkeypatch
) -> None:
    configure_structlog()
    monkeypatch.setattr(audit_middleware, "logger", get_logger("audit-log-test"))
    middleware = AuditMiddleware(
        audit_log=CapturingAuditLog(),  # type: ignore[arg-type]
        requester_resolver=StaticRequesterResolver(
            Requester(actor_id="actor", employee_id=42, roles=frozenset({"employee"}))
        ),
        correlation_id_provider=lambda: UUID("11111111-1111-1111-1111-111111111111"),
    )
    context = SimpleNamespace(message=SimpleNamespace(name="future_tool", arguments={}))

    with pytest.raises(ToolError, match='"INTERNAL_ERROR"'):
        asyncio.run(
            middleware.on_call_tool(
                context, lambda _context: _tool_result_with_sensitive_diagnostic()
            )
        )

    event = json.loads(capsys.readouterr().err.strip().splitlines()[-1])
    assert event["event"] == "mcp_tool_interaction"
    assert event["tool_name"] == "future_tool"
    assert event["outcome"] == "failure"
    assert "exception" not in event
    assert "traceback" not in event
    assert "sensitive diagnostic sentinel" not in json.dumps(event)


def test_audit_persistence_failure_log_omits_exception_details(
    capsys, monkeypatch
) -> None:
    configure_structlog()
    monkeypatch.setattr(audit_middleware, "logger", get_logger("audit-log-test"))
    middleware = AuditMiddleware(
        audit_log=FailingAuditLog(),  # type: ignore[arg-type]
        requester_resolver=StaticRequesterResolver(
            Requester(actor_id="actor", employee_id=42, roles=frozenset({"employee"}))
        ),
        correlation_id_provider=lambda: UUID("11111111-1111-1111-1111-111111111111"),
    )
    context = SimpleNamespace(message=SimpleNamespace(name="future_tool", arguments={}))

    with pytest.raises(ToolError, match='"BACKEND_UNAVAILABLE"'):
        asyncio.run(
            middleware.on_call_tool(context, lambda _context: _successful_tool_result())
        )

    event = json.loads(capsys.readouterr().err.strip().splitlines()[-1])
    assert event["event"] == "mcp_audit_persistence_failed"
    assert event["tool_name"] == "future_tool"
    assert event["outcome"] == "success"
    assert event["level"] == "error"
    assert "timestamp" in event
    assert "exception" not in event
    assert "traceback" not in event
    assert "audit database unavailable" not in json.dumps(event)
