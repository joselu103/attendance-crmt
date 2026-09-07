"""Public REST behavior for protected operation execution."""

import asyncio
from dataclasses import replace
from typing import Annotated

import httpx
from fastapi import Depends
from fastmcp.server.auth import AccessToken
from starlette.exceptions import HTTPException

from attendance_crmt.audit import AuditEvent
from attendance_crmt.identity import AuthenticatedTokenRequesterResolver
from attendance_crmt.rest import ProtectedOperation, create_app, get_protected_operation
from attendance_crmt.security_errors import SecurityFailure

CORRELATION_ID = "11111111-1111-1111-1111-111111111111"


class StaticTokenVerifier:
    """Return one already verified delegated token."""

    async def verify_token(self, token: str) -> AccessToken | None:
        if token != "delegated-token":
            return None
        return AccessToken(
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
            requester_resolver=resolver,
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
        assert session.query(AuditEvent).count() == 0


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
        async def verify_token(self, _token: str) -> AccessToken | None:
            raise RuntimeError("token=secret claims={} https://database.example")

    class UnusedPrincipalResolver:
        def resolve_access_token(self, _access_token: AccessToken | None):
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
