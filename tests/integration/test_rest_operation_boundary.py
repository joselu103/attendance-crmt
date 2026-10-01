"""Public REST behavior for protected operation execution."""

import asyncio
import json
from dataclasses import replace
from typing import Annotated

import httpx
import pytest
from fastapi import Depends
from starlette.exceptions import HTTPException
from structlog.testing import capture_logs

from attendance_crmt.audit import AuditEvent
from attendance_crmt.authentication import VerifiedDelegatedAccessToken
from attendance_crmt.identity import AuthenticatedTokenRequesterResolver, Principal
from attendance_crmt.rest import (
    ProtectedOperation,
    create_app,
    get_principal,
    get_protected_operation,
)
from attendance_crmt.security_errors import SecurityFailure

CORRELATION_ID = "11111111-1111-1111-1111-111111111111"


class StaticTokenVerifier:
    """Return one already verified delegated token."""

    async def verify_token(self, token: str) -> VerifiedDelegatedAccessToken | None:
        if token != "delegated-token":
            return None
        return VerifiedDelegatedAccessToken(
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


def _get(app, path: str, *, headers: list[tuple[str, str]]) -> httpx.Response:
    async def request() -> httpx.Response:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://test",
        ) as client:
            return await client.get(path, headers=headers)

    return asyncio.run(request())


def _protected_app(server_dependencies, employee_factory, *, audit_log=None):
    employee = employee_factory.build(izvajalec_id=42, email="person@example.com")
    with server_dependencies.attendance_session_factory() as session:
        session.add(employee)
        session.commit()

    resolver = AuthenticatedTokenRequesterResolver(
        session_factory=server_dependencies.attendance_session_factory,
        admin_role="attendance.admin",
    )
    app = create_app(
        replace(
            server_dependencies,
            auth_provider=StaticTokenVerifier(),  # type: ignore[arg-type]
            principal_resolver=resolver,
            **({"audit_log": audit_log} if audit_log is not None else {}),
        )
    )

    @app.get("/protected")
    async def protected_route(
        operation: Annotated[ProtectedOperation, Depends(get_protected_operation)],
    ) -> dict[str, str]:
        return await operation.execute(
            name="test.protected",
            action=lambda: {"status": "ok"},
        )

    @app.get("/failure")
    async def failure_route(
        operation: Annotated[ProtectedOperation, Depends(get_protected_operation)],
    ) -> dict[str, str]:
        def fail() -> dict[str, str]:
            raise RuntimeError("token=secret claims={} SELECT * FROM attendance")

        return await operation.execute(
            name="test.failure",
            action=fail,
        )

    @app.get("/validated")
    async def validated_route(
        operation: Annotated[ProtectedOperation, Depends(get_protected_operation)],
        page: int,
    ) -> dict[str, str]:
        return await operation.execute(
            name="test.validated",
            action=lambda: {"status": "ok"},
        )

    @app.get("/direct-success")
    async def direct_success_route(
        _: Annotated[ProtectedOperation, Depends(get_protected_operation)],
    ) -> dict[str, str]:
        return {"status": "ok"}

    return app


def _headers() -> list[tuple[str, str]]:
    return [
        ("Authorization", "Bearer delegated-token"),
        ("X-Correlation-ID", CORRELATION_ID),
    ]


def _validate_page(page: int) -> int:
    """Validate a protected request's query parameter."""
    return page


async def _principal_after_page_validation(
    _: Annotated[int, Depends(_validate_page)],
    principal: Annotated[Principal, Depends(get_principal)],
) -> Principal:
    """Use validated input before continuing through principal resolution."""
    return principal


def test_protected_rest_operation_records_one_correlation_linked_success(
    server_dependencies, employee_factory, audit_session_factory
) -> None:
    response = _get(
        _protected_app(server_dependencies, employee_factory),
        "/protected",
        headers=_headers(),
    )

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert response.headers["X-Attendance-API-Contract-Version"] == "1.0.0"
    with audit_session_factory() as session:
        events = session.query(AuditEvent).all()
    assert len(events) == 1
    assert events[0].correlation_id == CORRELATION_ID
    assert events[0].tool_name == "test.protected"
    assert events[0].outcome == "success"
    assert events[0].error_code is None
    assert events[0].request_json == "{}"


def test_direct_protected_rest_success_is_audited_once(
    server_dependencies, employee_factory, audit_session_factory
) -> None:
    response = _get(
        _protected_app(server_dependencies, employee_factory),
        "/direct-success",
        headers=_headers(),
    )

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    with audit_session_factory() as session:
        events = session.query(AuditEvent).all()
    assert len(events) == 1
    assert events[0].correlation_id == CORRELATION_ID
    assert events[0].tool_name == "rest:/direct-success"
    assert events[0].outcome == "success"
    assert events[0].error_code is None


def test_protected_rest_operation_hides_unexpected_failure_diagnostics(
    server_dependencies, employee_factory, audit_session_factory
) -> None:
    response = _get(
        _protected_app(server_dependencies, employee_factory),
        "/failure",
        headers=_headers(),
    )

    assert response.status_code == 500
    assert response.json() == {
        "code": "INTERNAL_ERROR",
        "message": "Attendance could not complete that request.",
    }
    assert "token=secret" not in response.text
    assert "SELECT" not in response.text
    assert response.headers["X-Attendance-API-Contract-Version"] == "1.0.0"
    with audit_session_factory() as session:
        event = session.query(AuditEvent).one()
    assert event.outcome == "failure"
    assert event.error_code == "INTERNAL_ERROR"


class FailingAuditLog:
    """Simulate an unavailable durable audit store."""

    def record(self, **_kwargs) -> None:
        raise OSError("audit store unavailable")


def test_protected_rest_operation_withholds_success_when_audit_persistence_fails(
    server_dependencies, employee_factory
) -> None:
    response = _get(
        _protected_app(
            server_dependencies, employee_factory, audit_log=FailingAuditLog()
        ),
        "/protected",
        headers=_headers(),
    )

    assert response.status_code == 503
    assert response.json() == {
        "code": "BACKEND_UNAVAILABLE",
        "message": "Attendance is temporarily unavailable. Please try again shortly.",
    }
    assert "status" not in response.text
    assert response.headers["X-Attendance-API-Contract-Version"] == "1.0.0"


def test_direct_protected_success_fails_closed_when_audit_persistence_fails(
    server_dependencies, employee_factory
) -> None:
    response = _get(
        _protected_app(
            server_dependencies, employee_factory, audit_log=FailingAuditLog()
        ),
        "/direct-success",
        headers=_headers(),
    )

    assert response.status_code == 503
    assert response.json() == {
        "code": "BACKEND_UNAVAILABLE",
        "message": "Attendance is temporarily unavailable. Please try again shortly.",
    }
    assert "status" not in response.text


def test_protected_rest_operation_rejects_missing_correlation_before_execution(
    server_dependencies, employee_factory, audit_session_factory
) -> None:
    response = _get(
        _protected_app(server_dependencies, employee_factory),
        "/protected",
        headers=[("Authorization", "Bearer delegated-token")],
    )

    assert response.status_code == 400
    assert response.json() == {
        "code": "CORRELATION_ID_INVALID",
        "message": "The request correlation ID is missing or invalid.",
    }
    with audit_session_factory() as session:
        events = session.query(AuditEvent).all()
    assert len(events) == 1
    assert events[0].actor_id == "unresolved"
    assert events[0].correlation_id != CORRELATION_ID
    assert events[0].tool_name == "rest:/protected"
    assert events[0].request_json == "{}"
    assert events[0].outcome == "failure"
    assert events[0].error_code == "CORRELATION_ID_INVALID"


@pytest.mark.parametrize(
    ("headers", "code"),
    [
        (
            [
                ("Authorization", "Bearer delegated-token"),
                ("X-Correlation-ID", "not-a-uuid"),
            ],
            "CORRELATION_ID_INVALID",
        ),
        (
            [
                ("Authorization", "Bearer delegated-token"),
                ("X-Correlation-ID", CORRELATION_ID),
                ("X-Correlation-ID", CORRELATION_ID),
            ],
            "CORRELATION_ID_INVALID",
        ),
        ([("X-Correlation-ID", CORRELATION_ID)], "AUTHENTICATION_REQUIRED"),
        (
            [("Authorization", "Basic token"), ("X-Correlation-ID", CORRELATION_ID)],
            "TOKEN_INVALID",
        ),
        (
            [
                ("Authorization", "Bearer invalid-token"),
                ("X-Correlation-ID", CORRELATION_ID),
            ],
            "TOKEN_INVALID",
        ),
    ],
    ids=(
        "malformed-correlation",
        "duplicate-correlation",
        "missing-bearer",
        "malformed-bearer",
        "invalid-bearer",
    ),
)
def test_protected_rest_early_rejections_are_audited_once(
    server_dependencies,
    employee_factory,
    audit_session_factory,
    headers: list[tuple[str, str]],
    code: str,
) -> None:
    response = _get(
        _protected_app(server_dependencies, employee_factory),
        "/protected",
        headers=headers,
    )

    assert response.json()["code"] == code
    with audit_session_factory() as session:
        events = session.query(AuditEvent).all()
    assert len(events) == 1
    assert events[0].actor_id == "unresolved"
    assert events[0].employee_id is None
    assert events[0].roles_json == "[]"
    assert events[0].tool_name == "rest:/protected"
    assert events[0].request_json == "{}"
    assert events[0].outcome == "failure"
    assert events[0].error_code == code
    if code == "CORRELATION_ID_INVALID":
        assert events[0].correlation_id != CORRELATION_ID
    else:
        assert events[0].correlation_id == CORRELATION_ID


def test_protected_request_validation_failure_is_audited(
    server_dependencies, employee_factory, audit_session_factory
) -> None:
    app = _protected_app(server_dependencies, employee_factory)

    @app.get("/validated-before-principal")
    async def validated_before_principal_route(
        _: Annotated[Principal, Depends(_principal_after_page_validation)],
    ) -> dict[str, str]:
        return {"status": "ok"}

    response = _get(
        app,
        "/validated-before-principal?page=not-an-integer",
        headers=_headers(),
    )

    assert response.status_code == 400
    with audit_session_factory() as session:
        event = session.query(AuditEvent).one()
    assert event.tool_name == "rest:/validated-before-principal"
    assert event.request_json == "{}"
    assert event.error_code == "INVALID_ARGUMENT"


def test_identity_mapping_failure_before_principal_is_audited(
    server_dependencies, audit_session_factory
) -> None:
    resolver = AuthenticatedTokenRequesterResolver(
        session_factory=server_dependencies.attendance_session_factory,
        admin_role="attendance.admin",
    )
    app = create_app(
        replace(
            server_dependencies,
            auth_provider=StaticTokenVerifier(),  # type: ignore[arg-type]
            principal_resolver=resolver,
        )
    )

    @app.get("/identity-mapping")
    async def identity_mapping_route(
        _: Annotated[ProtectedOperation, Depends(get_protected_operation)],
    ) -> dict[str, str]:
        return {"status": "ok"}

    response = _get(app, "/identity-mapping", headers=_headers())

    assert response.status_code == 403
    assert response.json()["code"] == "IDENTITY_UNMAPPED"
    with audit_session_factory() as session:
        event = session.query(AuditEvent).one()
    assert event.actor_id == "unresolved"
    assert event.tool_name == "rest:/identity-mapping"
    assert event.request_json == "{}"
    assert event.error_code == "IDENTITY_UNMAPPED"


def test_early_protected_rejection_fails_closed_when_audit_persistence_fails(
    server_dependencies, employee_factory
) -> None:
    response = _get(
        _protected_app(
            server_dependencies, employee_factory, audit_log=FailingAuditLog()
        ),
        "/protected",
        headers=[("X-Correlation-ID", CORRELATION_ID)],
    )

    assert response.status_code == 503
    assert response.json()["code"] == "BACKEND_UNAVAILABLE"


def test_protected_rest_validation_failure_hides_raw_input(
    server_dependencies, employee_factory, audit_session_factory
) -> None:
    response = _get(
        _protected_app(server_dependencies, employee_factory),
        "/validated?page=token%3Dsecret",
        headers=_headers(),
    )

    assert response.status_code == 400
    assert response.json() == {
        "code": "INVALID_ARGUMENT",
        "message": "Check the attendance date range and pagination values and try again.",
    }
    assert "token=secret" not in response.text
    assert response.headers["X-Attendance-API-Contract-Version"] == "1.0.0"
    with audit_session_factory() as session:
        event = session.query(AuditEvent).one()
    assert event.tool_name == "rest:/validated"
    assert event.outcome == "failure"
    assert event.error_code == "INVALID_ARGUMENT"
    assert event.request_json == "{}"


def test_protected_rest_dependency_failure_hides_verifier_diagnostics(
    server_dependencies,
) -> None:
    class FailingTokenVerifier:
        async def verify_token(
            self, _token: str
        ) -> VerifiedDelegatedAccessToken | None:
            raise RuntimeError("token=secret claims={} https://database.example")

    class UnusedPrincipalResolver:
        def resolve_access_token(
            self, _access_token: VerifiedDelegatedAccessToken | None
        ):
            raise AssertionError("the verifier failure must stop principal resolution")

    app = create_app(
        replace(
            server_dependencies,
            auth_provider=FailingTokenVerifier(),  # type: ignore[arg-type]
            principal_resolver=UnusedPrincipalResolver(),  # type: ignore[arg-type]
        )
    )

    @app.get("/protected")
    async def protected_route(
        _: Annotated[ProtectedOperation, Depends(get_protected_operation)],
    ) -> dict[str, str]:
        return {"status": "ok"}

    response = _get(app, "/protected", headers=_headers())

    assert response.status_code == 500
    assert response.json() == {
        "code": "INTERNAL_ERROR",
        "message": "Attendance could not complete that request.",
    }
    assert "token=secret" not in response.text
    assert "database.example" not in response.text
    assert response.headers["X-Attendance-API-Contract-Version"] == "1.0.0"


def test_protected_rest_http_failure_hides_raw_detail(
    server_dependencies, employee_factory, audit_session_factory
) -> None:
    app = _protected_app(server_dependencies, employee_factory)

    @app.get("/http-failure")
    async def http_failure_route(
        _: Annotated[ProtectedOperation, Depends(get_protected_operation)],
    ) -> None:
        raise HTTPException(
            status_code=404,
            detail="token=secret claims={} SELECT * FROM attendance",
        )

    response = _get(app, "/http-failure", headers=_headers())

    assert response.status_code == 404
    assert response.json() == {
        "code": "NOT_FOUND",
        "message": "The requested attendance resource was not found.",
    }
    assert "token=secret" not in response.text
    assert "SELECT" not in response.text
    assert response.headers["X-Attendance-API-Contract-Version"] == "1.0.0"
    with audit_session_factory() as session:
        event = session.query(AuditEvent).one()
    assert event.correlation_id == CORRELATION_ID
    assert event.tool_name == "rest:/http-failure"
    assert event.outcome == "failure"
    assert event.error_code == "NOT_FOUND"


def test_protected_rest_direct_failure_records_safe_audit_event(
    server_dependencies, employee_factory, audit_session_factory
) -> None:
    app = _protected_app(server_dependencies, employee_factory)

    @app.get("/direct-failure")
    async def direct_failure_route(
        _: Annotated[ProtectedOperation, Depends(get_protected_operation)],
    ) -> None:
        raise RuntimeError("token=secret claims={} SELECT * FROM attendance")

    response = _get(app, "/direct-failure", headers=_headers())

    assert response.status_code == 500
    assert response.json() == {
        "code": "INTERNAL_ERROR",
        "message": "Attendance could not complete that request.",
    }
    assert "token=secret" not in response.text
    with audit_session_factory() as session:
        event = session.query(AuditEvent).one()
    assert event.correlation_id == CORRELATION_ID
    assert event.tool_name == "rest:/direct-failure"
    assert event.outcome == "failure"
    assert event.error_code == "INTERNAL_ERROR"


def test_protected_rest_direct_security_failure_records_safe_audit_event(
    server_dependencies, employee_factory, audit_session_factory
) -> None:
    app = _protected_app(server_dependencies, employee_factory)

    @app.get("/direct-security-failure")
    async def direct_security_failure_route(
        _: Annotated[ProtectedOperation, Depends(get_protected_operation)],
    ) -> None:
        raise SecurityFailure(code="FORBIDDEN")

    response = _get(app, "/direct-security-failure", headers=_headers())

    assert response.status_code == 403
    assert response.json() == {
        "code": "FORBIDDEN",
        "message": "You do not have permission to do that.",
    }
    with audit_session_factory() as session:
        event = session.query(AuditEvent).one()
    assert event.correlation_id == CORRELATION_ID
    assert event.tool_name == "rest:/direct-security-failure"
    assert event.outcome == "failure"
    assert event.error_code == "FORBIDDEN"


def test_executed_rest_operation_preserves_safe_http_failure_code(
    server_dependencies, employee_factory, audit_session_factory
) -> None:
    app = _protected_app(server_dependencies, employee_factory)

    @app.get("/executed-http-failure")
    async def http_failure_route(
        operation: Annotated[ProtectedOperation, Depends(get_protected_operation)],
    ) -> object:
        def fail() -> None:
            raise HTTPException(status_code=404, detail="raw resource detail")

        return await operation.execute(name="test.executed-http", action=fail)

    response = _get(app, "/executed-http-failure", headers=_headers())

    assert response.status_code == 404
    assert response.json() == {
        "code": "NOT_FOUND",
        "message": "The requested attendance resource was not found.",
    }
    assert "raw resource detail" not in response.text
    with audit_session_factory() as session:
        event = session.query(AuditEvent).one()
    assert event.tool_name == "test.executed-http"
    assert event.outcome == "failure"
    assert event.error_code == "NOT_FOUND"


def test_rest_success_emits_correlated_request_and_operation_lifecycle_events(
    server_dependencies, employee_factory
) -> None:
    with capture_logs() as logs:
        response = _get(
            _protected_app(server_dependencies, employee_factory),
            "/protected",
            headers=_headers(),
        )

    assert response.status_code == 200
    events = {event["event"]: event for event in logs}
    assert events["request_received"]["route"] == "/protected"
    assert events["request_completed"] == {
        "event": "request_completed",
        "log_level": "info",
        "trace_id": events["request_received"]["trace_id"],
        "correlation_id": CORRELATION_ID,
        "route": "/protected",
        "status_code": 200,
        "state": "completed",
        "duration_ms": events["request_completed"]["duration_ms"],
    }
    assert events["operation_started"]["handler"] == "test.protected"
    assert events["operation_started"]["inputs"] == {}
    assert events["operation_started"]["correlation_id"] == CORRELATION_ID
    assert events["operation_step"]["state"] == "action_completed"
    assert events["operation_succeeded"]["state"] == "success"
    assert all(event["log_level"] == "info" for event in logs)


def test_rest_validation_failure_emits_safe_warning_lifecycle_events(
    server_dependencies, employee_factory
) -> None:
    with capture_logs() as logs:
        response = _get(
            _protected_app(server_dependencies, employee_factory),
            "/validated?page=token%3Dsecret",
            headers=_headers(),
        )

    assert response.status_code == 400
    events = {event["event"]: event for event in logs}
    assert events["request_failed"]["log_level"] == "warning"
    assert events["request_failed"]["status_code"] == 400
    assert events["operation_failed"] == {
        "event": "operation_failed",
        "log_level": "warning",
        "correlation_id": CORRELATION_ID,
        "handler": "rest:/validated",
        "inputs": {},
        "state": "failure",
        "error_code": "INVALID_ARGUMENT",
        "duration_ms": events["operation_failed"]["duration_ms"],
    }
    assert "secret" not in json.dumps(logs)


def test_rest_runtime_failure_emits_safe_error_lifecycle_events(
    server_dependencies, employee_factory
) -> None:
    with capture_logs() as logs:
        response = _get(
            _protected_app(server_dependencies, employee_factory),
            "/failure",
            headers=_headers(),
        )

    assert response.status_code == 500
    events = {event["event"]: event for event in logs}
    assert events["request_failed"]["log_level"] == "error"
    assert events["request_failed"]["status_code"] == 500
    assert events["operation_failed"]["log_level"] == "error"
    assert events["operation_failed"]["error_code"] == "INTERNAL_ERROR"
    assert "secret" not in json.dumps(logs)
