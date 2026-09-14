"""FastAPI REST composition, protected operation, and safe error seams."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from inspect import isawaitable
from time import perf_counter
from typing import Annotated, TypeVar
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from fastapi import Depends, FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastmcp.server.auth import AccessToken
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker
from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse, Response
from starlette.routing import Match
from starlette.types import Lifespan

from attendance_crmt.attendance.contracts import (
    AttendanceEventQuery,
    AttendanceExceptionsQuery,
    CurrentAttendanceQuery,
    DailyAttendanceQuery,
    EmployeeAttendanceAnalysisQuery,
    LiveAttendanceStatus,
    MyAttendanceEventQuery,
    OrganizationAttendanceAnalysisQuery,
    PlannedWorkQuery,
)
from attendance_crmt.attendance.services import (
    get_attendance_event,
    get_attendance_exceptions,
    get_daily_attendance,
    get_employee_attendance_analysis,
    get_employee_attendance_summary,
    get_organization_attendance_analysis,
    get_planned_work,
    list_attendance_events,
    list_current_attendance,
    list_my_attendance_events,
)
from attendance_crmt.catalog.contracts import EmployeePageQuery
from attendance_crmt.catalog.services import (
    get_employee,
    list_active_employees,
    list_locations,
    list_punch_types,
)
from attendance_crmt.dependencies import ServerDependencies
from attendance_crmt.http_contract import CORRELATION_ID_HEADER
from attendance_crmt.identity import Principal
from attendance_crmt.observability import (
    bind_identity_context,
    get_logger,
    log_permission_denied,
    reset_identity_context,
)
from attendance_crmt.security_errors import (
    SECURITY_ERROR_MESSAGES,
    SECURITY_ERROR_STATUS_CODES,
    SecurityErrorCode,
    SecurityErrorResponse,
    SecurityFailure,
)

Result = TypeVar("Result")

REST_CONTRACT_VERSION = "1.0.0"
REST_CONTRACT_VERSION_HEADER = "X-Attendance-API-Contract-Version"
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
    """Return a non-negative monotonic duration suitable for structured logs."""
    return round((perf_counter() - started_at) * 1000)


def _request_route(request: Request) -> str:
    """Resolve the route template without retaining path or query values."""
    for route in request.app.router.routes:
        match, _ = route.matches(request.scope)
        if match is not Match.NONE:
            path = getattr(route, "path", None)
            if isinstance(path, str):
                return path
    return "unknown"


def _safe_correlation_id(request: Request) -> str | None:
    """Return only a validated correlation identifier for lifecycle logs."""
    values = request.headers.getlist(CORRELATION_ID_HEADER)
    if len(values) != 1:
        return None
    try:
        return str(UUID(values[0]))
    except ValueError:
        return None


def _log_operation_failure(
    *, name: str, correlation_id: UUID, code: SecurityErrorCode, started_at: float
) -> None:
    """Emit a safe terminal event without operation inputs or diagnostics."""
    log = logger.warning if code in _CLIENT_ERROR_CODES else logger.error
    log(
        "operation_failed",
        correlation_id=str(correlation_id),
        handler=name,
        inputs={},
        state="failure",
        error_code=code,
        duration_ms=_duration_ms(started_at),
    )


def current_attendance_query(
    as_of: datetime | None = None,
    status: LiveAttendanceStatus | None = None,
    limit: int = 50,
    offset: int = 0,
) -> CurrentAttendanceQuery:
    """Build the current-attendance query with the established local default."""
    try:
        return CurrentAttendanceQuery(
            as_of=as_of
            or datetime.now(ZoneInfo("Europe/Ljubljana")).replace(tzinfo=None),
            status=status,
            limit=limit,
            offset=offset,
        )
    except ValidationError:
        raise SecurityFailure(code="INVALID_ARGUMENT") from None


def _bearer_token(request: Request) -> str:
    """Read exactly one syntactically valid delegated bearer credential."""
    values = request.headers.getlist("authorization")
    if not values:
        raise SecurityFailure(code="AUTHENTICATION_REQUIRED")
    if len(values) != 1:
        raise SecurityFailure(code="TOKEN_INVALID")

    scheme, separator, credential = values[0].partition(" ")
    if scheme.casefold() != "bearer" or not separator or not credential.strip():
        raise SecurityFailure(code="TOKEN_INVALID")
    return credential.strip()


async def get_principal(request: Request):
    """FastAPI dependency that verifies a bearer and derives one Principal."""
    request.state.protected_route = True
    dependencies: ServerDependencies | None = request.app.state.dependencies
    if dependencies is None or dependencies.auth_provider is None:
        raise SecurityFailure(code="TOKEN_INVALID")
    if dependencies.principal_resolver is None:
        raise SecurityFailure(code="TOKEN_INVALID")

    verifier: Callable[[str], Awaitable[AccessToken | None]] = (
        dependencies.auth_provider.verify_token
    )
    access_token = await verifier(_bearer_token(request))
    principal = dependencies.principal_resolver.resolve_access_token(access_token)
    request.state.protected_operation = ProtectedOperation(
        dependencies=dependencies,
        principal=principal,
        correlation_id=_correlation_id(request),
        request=request,
    )
    context_tokens = bind_identity_context(
        subject=principal.actor_id, client_id=principal.client_id
    )
    try:
        yield principal
    finally:
        reset_identity_context(context_tokens)


def _correlation_id(request: Request) -> UUID:
    values = request.headers.getlist(CORRELATION_ID_HEADER)
    if len(values) != 1:
        raise SecurityFailure(code="CORRELATION_ID_INVALID")
    try:
        return UUID(values[0])
    except ValueError:
        raise SecurityFailure(code="CORRELATION_ID_INVALID") from None


def _failure_code(error: Exception) -> SecurityErrorCode:
    if isinstance(error, HTTPException):
        return _http_failure_code(error)
    if isinstance(error, SecurityFailure):
        return error.code
    if isinstance(error, PermissionError):
        return "FORBIDDEN"
    if isinstance(error, LookupError):
        return "NOT_FOUND"
    if isinstance(error, SQLAlchemyError):
        return "BACKEND_UNAVAILABLE"
    return "INTERNAL_ERROR"


def _http_failure_code(error: HTTPException) -> SecurityErrorCode:
    return {
        400: "INVALID_ARGUMENT",
        401: "TOKEN_INVALID",
        403: "FORBIDDEN",
        404: "NOT_FOUND",
        503: "BACKEND_UNAVAILABLE",
    }.get(error.status_code, "INTERNAL_ERROR")


class RestOperationFailure(Exception):
    """Private signal that an operation must return a fixed safe REST error."""

    def __init__(self, code: SecurityErrorCode) -> None:
        self.code = code


@dataclass(frozen=True)
class ProtectedOperation:
    """Execute exactly one resolved REST operation with mandatory auditing."""

    dependencies: ServerDependencies
    principal: Principal
    correlation_id: UUID
    request: Request

    async def execute(
        self,
        *,
        name: str,
        action: Callable[[], Result | Awaitable[Result]],
    ) -> Response:
        """Run an operation, then durably record its one safe outcome."""
        started_at = perf_counter()
        logger.info(
            "operation_started",
            correlation_id=str(self.correlation_id),
            handler=name,
            inputs={},
            state="started",
        )
        try:
            result = action()
            if isawaitable(result):
                result = await result
            logger.info(
                "operation_step",
                correlation_id=str(self.correlation_id),
                handler=name,
                inputs={},
                state="action_completed",
                duration_ms=_duration_ms(started_at),
            )
            response = JSONResponse(content=jsonable_encoder(result))
        except Exception as error:  # noqa: BLE001
            code = _failure_code(error)
            if code == "FORBIDDEN":
                log_permission_denied(
                    subject=self.principal.actor_id, client_id=self.principal.client_id
                )
            try:
                await self._record_or_raise(
                    name=name,
                    outcome="failure",
                    error_code=code,
                    started_at=started_at,
                )
            except RestOperationFailure as audit_error:
                _log_operation_failure(
                    name=name,
                    correlation_id=self.correlation_id,
                    code=audit_error.code,
                    started_at=started_at,
                )
                raise
            _log_operation_failure(
                name=name,
                correlation_id=self.correlation_id,
                code=code,
                started_at=started_at,
            )
            raise RestOperationFailure(code) from None

        try:
            await self._record_or_raise(
                name=name,
                outcome="success",
                error_code=None,
                started_at=started_at,
            )
        except RestOperationFailure as error:
            _log_operation_failure(
                name=name,
                correlation_id=self.correlation_id,
                code=error.code,
                started_at=started_at,
            )
            raise
        logger.info(
            "operation_succeeded",
            correlation_id=str(self.correlation_id),
            handler=name,
            inputs={},
            state="success",
            duration_ms=_duration_ms(started_at),
        )
        return response

    async def record_failure(self, *, name: str, code: SecurityErrorCode) -> None:
        """Persist a fixed failure without retaining rejected input."""
        started_at = perf_counter()
        logger.info(
            "operation_started",
            correlation_id=str(self.correlation_id),
            handler=name,
            inputs={},
            state="started",
        )
        logger.info(
            "operation_step",
            correlation_id=str(self.correlation_id),
            handler=name,
            inputs={},
            state="failure_classified",
            duration_ms=_duration_ms(started_at),
        )
        try:
            await self._record_or_raise(
                name=name,
                outcome="failure",
                error_code=code,
                started_at=started_at,
            )
        except RestOperationFailure as error:
            _log_operation_failure(
                name=name,
                correlation_id=self.correlation_id,
                code=error.code,
                started_at=started_at,
            )
            raise
        _log_operation_failure(
            name=name,
            correlation_id=self.correlation_id,
            code=code,
            started_at=started_at,
        )

    async def record_success_if_needed(self, *, name: str) -> None:
        """Durably record a direct protected-route success exactly once."""
        if getattr(self.request.state, "audit_recorded", False):
            return
        started_at = perf_counter()
        logger.info(
            "operation_started",
            correlation_id=str(self.correlation_id),
            handler=name,
            inputs={},
            state="started",
        )
        logger.info(
            "operation_step",
            correlation_id=str(self.correlation_id),
            handler=name,
            inputs={},
            state="handler_completed",
            duration_ms=_duration_ms(started_at),
        )
        try:
            await self._record_or_raise(
                name=name,
                outcome="success",
                error_code=None,
                started_at=started_at,
            )
        except RestOperationFailure as error:
            _log_operation_failure(
                name=name,
                correlation_id=self.correlation_id,
                code=error.code,
                started_at=started_at,
            )
            raise
        logger.info(
            "operation_succeeded",
            correlation_id=str(self.correlation_id),
            handler=name,
            inputs={},
            state="success",
            duration_ms=_duration_ms(started_at),
        )

    async def _record_or_raise(
        self,
        *,
        name: str,
        outcome: str,
        error_code: SecurityErrorCode | None,
        started_at: float,
    ) -> None:
        try:
            audit_log = self.dependencies.audit_log
            audit_log.record(
                actor_id=self.principal.actor_id,
                employee_id=self.principal.employee_id,
                roles=self.principal.roles,
                correlation_id=self.correlation_id,
                tool_name=name,
                request={},
                outcome=outcome,
                error_code=error_code,
                duration_ms=round((perf_counter() - started_at) * 1000),
            )
            self.request.state.audit_recorded = True
        except Exception:  # noqa: BLE001
            raise RestOperationFailure("BACKEND_UNAVAILABLE") from None


async def get_protected_operation(
    request: Request, principal: Annotated[Principal, Depends(get_principal)]
) -> ProtectedOperation:
    """Resolve one authenticated principal and correlation ID for a REST operation."""
    operation = getattr(request.state, "protected_operation", None)
    if not isinstance(operation, ProtectedOperation):
        raise SecurityFailure(code="BACKEND_UNAVAILABLE")
    if operation.principal != principal:
        raise SecurityFailure(code="INTERNAL_ERROR")
    return operation


def _safe_error_response(code: SecurityErrorCode) -> JSONResponse:
    response = SecurityErrorResponse(code=code, message=SECURITY_ERROR_MESSAGES[code])
    return JSONResponse(
        status_code=SECURITY_ERROR_STATUS_CODES[code], content=response.model_dump()
    )


def _protected_safe_error_response(
    request: Request, code: SecurityErrorCode
) -> JSONResponse:
    response = _safe_error_response(code)
    if getattr(request.state, "protected_route", False):
        response.headers[REST_CONTRACT_VERSION_HEADER] = REST_CONTRACT_VERSION
    return response


async def _record_resolved_failure(
    request: Request, code: SecurityErrorCode
) -> SecurityErrorCode:
    operation = getattr(request.state, "protected_operation", None)
    if not isinstance(operation, ProtectedOperation):
        return code
    if code == "FORBIDDEN":
        log_permission_denied(
            subject=operation.principal.actor_id,
            client_id=operation.principal.client_id,
        )
    try:
        route = request.scope.get("route")
        route_path = getattr(route, "path", "unknown")
        await operation.record_failure(name=f"rest:{route_path}", code=code)
    except RestOperationFailure as error:
        return error.code
    return code


def create_app(
    dependencies: ServerDependencies | None = None,
    *,
    lifespan: Lifespan[FastAPI] | None = None,
) -> FastAPI:
    """Create the REST shell from optional, explicitly injected dependencies."""
    app = FastAPI(
        openapi_url=None,
        docs_url=None,
        redoc_url=None,
        lifespan=lifespan,
    )
    app.state.dependencies = dependencies

    @app.middleware("http")
    async def rest_contract_version_response(request: Request, call_next) -> Response:
        started_at = perf_counter()
        trace_id = str(uuid4())
        route = _request_route(request)
        correlation_id = _safe_correlation_id(request)
        logger.info(
            "request_received",
            trace_id=trace_id,
            correlation_id=correlation_id,
            route=route,
            state="received",
        )
        try:
            response = await call_next(request)
        except Exception:
            logger.error(
                "request_failed",
                trace_id=trace_id,
                correlation_id=correlation_id,
                route=route,
                status_code=500,
                state="failed",
                duration_ms=_duration_ms(started_at),
            )
            raise
        operation = getattr(request.state, "protected_operation", None)
        if (
            isinstance(operation, ProtectedOperation)
            and 200 <= response.status_code < 400
        ):
            try:
                await operation.record_success_if_needed(name=f"rest:{route}")
            except RestOperationFailure as error:
                response = _protected_safe_error_response(request, error.code)
        if getattr(request.state, "protected_route", False):
            response.headers[REST_CONTRACT_VERSION_HEADER] = REST_CONTRACT_VERSION
        event = "request_completed" if response.status_code < 400 else "request_failed"
        log = (
            logger.info
            if event == "request_completed"
            else (logger.warning if response.status_code < 500 else logger.error)
        )
        log(
            event,
            trace_id=trace_id,
            correlation_id=correlation_id,
            route=route,
            status_code=response.status_code,
            state="completed" if event == "request_completed" else "failed",
            duration_ms=_duration_ms(started_at),
        )
        return response

    @app.exception_handler(SecurityFailure)
    async def security_failure_response(
        request: Request, error: SecurityFailure
    ) -> JSONResponse:
        return _protected_safe_error_response(
            request, await _record_resolved_failure(request, error.code)
        )

    @app.exception_handler(RestOperationFailure)
    async def operation_failure_response(
        request: Request, error: RestOperationFailure
    ) -> JSONResponse:
        return _protected_safe_error_response(request, error.code)

    @app.exception_handler(RequestValidationError)
    async def request_validation_failure_response(
        request: Request, _error: RequestValidationError
    ) -> JSONResponse:
        return _protected_safe_error_response(
            request, await _record_resolved_failure(request, "INVALID_ARGUMENT")
        )

    @app.exception_handler(Exception)
    async def unexpected_failure_response(
        request: Request, error: Exception
    ) -> JSONResponse:
        return _protected_safe_error_response(
            request,
            await _record_resolved_failure(request, _failure_code(error)),
        )

    @app.exception_handler(HTTPException)
    async def http_failure_response(
        request: Request, error: HTTPException
    ) -> JSONResponse:
        return _protected_safe_error_response(
            request,
            await _record_resolved_failure(request, _http_failure_code(error)),
        )

    @app.get("/health")
    async def health() -> dict[str, str]:
        """Report public process liveness without checking dependencies."""
        return {"status": "ok"}

    @app.post("/internal/v1/mcp/session-admissions", status_code=204)
    async def admit_mcp_session(
        _: Annotated[ProtectedOperation, Depends(get_protected_operation)],
    ) -> Response:
        """Admit an adapter MCP session without exposing the resolved principal."""
        return Response(status_code=204)

    @app.get("/api/v1/me/attendance-events")
    async def get_my_attendance_events(
        operation: Annotated[ProtectedOperation, Depends(get_protected_operation)],
        query: Annotated[MyAttendanceEventQuery, Depends()],
    ) -> Response:
        """Return one bounded page for the authenticated employee only."""
        return await operation.execute(
            name="rest:/api/v1/me/attendance-events",
            action=lambda: list_my_attendance_events(
                requester=operation.principal,
                session_factory=operation.dependencies.attendance_session_factory,
                query=query,
            ),
        )

    @app.get("/api/v1/employees")
    async def get_employees(
        operation: Annotated[ProtectedOperation, Depends(get_protected_operation)],
        query: Annotated[EmployeePageQuery, Depends()],
    ) -> Response:
        """Return one bounded page of active employee directory entries."""
        return await operation.execute(
            name="rest:/api/v1/employees",
            action=lambda: list_active_employees(
                session_factory=operation.dependencies.attendance_session_factory,
                query=query,
            ),
        )

    @app.get("/api/v1/employees/{employee_id}")
    async def get_employee_by_id(
        employee_id: int,
        operation: Annotated[ProtectedOperation, Depends(get_protected_operation)],
    ) -> Response:
        """Return one employee's established directory-safe representation."""
        return await operation.execute(
            name="rest:/api/v1/employees/{employee_id}",
            action=lambda: _get_employee_or_not_found(
                session_factory=operation.dependencies.attendance_session_factory,
                employee_id=employee_id,
            ),
        )

    @app.get("/api/v1/punch-types")
    async def get_punch_types(
        operation: Annotated[ProtectedOperation, Depends(get_protected_operation)],
        active_only: bool = True,
    ) -> Response:
        """Return configured punch types and their server-derived locations."""
        return await operation.execute(
            name="rest:/api/v1/punch-types",
            action=lambda: list_punch_types(
                session_factory=operation.dependencies.attendance_session_factory,
                active_only=active_only,
            ),
        )

    @app.get("/api/v1/locations")
    async def get_locations(
        operation: Annotated[ProtectedOperation, Depends(get_protected_operation)],
    ) -> Response:
        """Return recorded-attendance location reference data."""
        return await operation.execute(
            name="rest:/api/v1/locations",
            action=lambda: list_locations(
                session_factory=operation.dependencies.attendance_session_factory,
            ),
        )

    @app.get("/api/v1/attendance-events/{attendance_event_id}")
    async def get_attendance_event_detail(
        attendance_event_id: int,
        operation: Annotated[ProtectedOperation, Depends(get_protected_operation)],
    ) -> Response:
        """Return one administrator-authorized attendance event with audit metadata."""
        return await operation.execute(
            name="rest:/api/v1/attendance-events/{attendance_event_id}",
            action=lambda: get_attendance_event(
                requester=operation.principal,
                session_factory=operation.dependencies.attendance_session_factory,
                attendance_event_id=attendance_event_id,
            ),
        )

    @app.get("/api/v1/employees/{employee_id}/attendance-events")
    async def get_employee_attendance_events(
        employee_id: int,
        operation: Annotated[ProtectedOperation, Depends(get_protected_operation)],
        query: Annotated[AttendanceEventQuery, Depends()],
    ) -> Response:
        """Return an administrator-authorized bounded employee event page."""
        if query.employee_id != employee_id:
            raise SecurityFailure(code="INVALID_ARGUMENT")
        return await operation.execute(
            name="rest:/api/v1/employees/{employee_id}/attendance-events",
            action=lambda: list_attendance_events(
                requester=operation.principal,
                session_factory=operation.dependencies.attendance_session_factory,
                query=query,
            ),
        )

    @app.get("/api/v1/employees/{employee_id}/daily-attendance")
    async def get_employee_daily_attendance(
        employee_id: int,
        operation: Annotated[ProtectedOperation, Depends(get_protected_operation)],
        query: Annotated[DailyAttendanceQuery, Depends()],
    ) -> Response:
        """Return one administrator-authorized employee daily-attendance view."""
        if query.employee_id != employee_id:
            raise SecurityFailure(code="INVALID_ARGUMENT")
        return await operation.execute(
            name="rest:/api/v1/employees/{employee_id}/daily-attendance",
            action=lambda: get_daily_attendance(
                requester=operation.principal,
                session_factory=operation.dependencies.attendance_session_factory,
                query=query,
            ),
        )

    @app.get("/api/v1/employees/{employee_id}/planned-work")
    async def get_employee_planned_work(
        employee_id: int,
        operation: Annotated[ProtectedOperation, Depends(get_protected_operation)],
        query: Annotated[PlannedWorkQuery, Depends()],
    ) -> Response:
        """Return an administrator-authorized employee planned-work range."""
        if query.employee_id != employee_id:
            raise SecurityFailure(code="INVALID_ARGUMENT")
        return await operation.execute(
            name="rest:/api/v1/employees/{employee_id}/planned-work",
            action=lambda: get_planned_work(
                requester=operation.principal,
                session_factory=operation.dependencies.attendance_session_factory,
                query=query,
            ),
        )

    @app.get("/api/v1/attendance/current")
    async def get_current_attendance(
        operation: Annotated[ProtectedOperation, Depends(get_protected_operation)],
        query: Annotated[CurrentAttendanceQuery, Depends(current_attendance_query)],
    ) -> Response:
        """Return the current active-workforce attendance view."""
        return await operation.execute(
            name="rest:/api/v1/attendance/current",
            action=lambda: list_current_attendance(
                session_factory=operation.dependencies.attendance_session_factory,
                query=query,
            ),
        )

    @app.get("/api/v1/employees/{employee_id}/attendance-summary")
    async def get_employee_summary(
        operation: Annotated[ProtectedOperation, Depends(get_protected_operation)],
        query: Annotated[EmployeeAttendanceAnalysisQuery, Depends()],
    ) -> Response:
        """Return the administrator-authorized compact employee report."""
        return await operation.execute(
            name="rest:/api/v1/employees/{employee_id}/attendance-summary",
            action=lambda: get_employee_attendance_summary(
                requester=operation.principal,
                session_factory=operation.dependencies.attendance_session_factory,
                query=query,
            ),
        )

    @app.get("/api/v1/employees/{employee_id}/attendance-analysis")
    async def get_employee_analysis(
        operation: Annotated[ProtectedOperation, Depends(get_protected_operation)],
        query: Annotated[EmployeeAttendanceAnalysisQuery, Depends()],
    ) -> Response:
        """Return the administrator-authorized detailed employee report."""
        return await operation.execute(
            name="rest:/api/v1/employees/{employee_id}/attendance-analysis",
            action=lambda: get_employee_attendance_analysis(
                requester=operation.principal,
                session_factory=operation.dependencies.attendance_session_factory,
                query=query,
            ),
        )

    @app.get("/api/v1/attendance/organization-analysis")
    async def get_organization_analysis(
        operation: Annotated[ProtectedOperation, Depends(get_protected_operation)],
        query: Annotated[OrganizationAttendanceAnalysisQuery, Depends()],
    ) -> Response:
        """Return the administrator-authorized organization attendance report."""
        return await operation.execute(
            name="rest:/api/v1/attendance/organization-analysis",
            action=lambda: get_organization_attendance_analysis(
                requester=operation.principal,
                session_factory=operation.dependencies.attendance_session_factory,
                query=query,
            ),
        )

    @app.get("/api/v1/attendance/exceptions")
    async def get_exceptions(
        operation: Annotated[ProtectedOperation, Depends(get_protected_operation)],
        query: Annotated[AttendanceExceptionsQuery, Depends()],
    ) -> Response:
        """Return the administrator-authorized operational exception report."""
        return await operation.execute(
            name="rest:/api/v1/attendance/exceptions",
            action=lambda: get_attendance_exceptions(
                requester=operation.principal,
                session_factory=operation.dependencies.attendance_session_factory,
                query=query,
            ),
        )

    return app


def _get_employee_or_not_found(
    *, session_factory: sessionmaker[Session], employee_id: int
):
    """Adapt the catalog's absent-record signal to the frozen REST error."""
    try:
        return get_employee(session_factory=session_factory, employee_id=employee_id)
    except LookupError:
        raise HTTPException(status_code=404) from None
