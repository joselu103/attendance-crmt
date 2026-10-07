"""OpenAPI-only response models, examples, and safe-error metadata."""

from copy import deepcopy
from typing import Literal

from pydantic import BaseModel, ConfigDict

from attendance_crmt.security_errors import (
    SECURITY_ERROR_MESSAGES,
    SecurityErrorCode,
    SecurityErrorResponse,
)

SuccessExample = Literal[
    "event_page",
    "event",
    "my_summary",
    "employee_page",
    "employee",
    "punch_types",
    "locations",
    "event_detail",
    "daily_attendance",
    "planned_work",
    "current_attendance",
    "employee_summary",
    "employee_analysis",
    "organization_analysis",
    "exceptions",
]


class HealthResponse(BaseModel):
    """Public process-liveness response."""

    model_config = ConfigDict(frozen=True)

    status: str


def health_response_documentation() -> dict[int, dict[str, object]]:
    """Return the public liveness response documentation."""
    return {200: {"content": {"application/json": {"example": {"status": "ok"}}}}}


def protected_response_documentation(
    example: SuccessExample,
) -> dict[int, dict[str, object]]:
    """Return the operation-specific success documentation."""
    return {
        200: {
            "content": {
                "application/json": {"example": deepcopy(_SUCCESS_EXAMPLES[example])}
            }
        }
    }


def safe_error_response_components() -> dict[str, dict[str, object]]:
    """Return reusable OpenAPI components for the fixed safe error envelope."""
    return {
        "InvalidArgument": _error_response(
            "INVALID_ARGUMENT", "Invalid correlation ID or request arguments."
        ),
        "AuthenticationRequired": _error_response(
            "AUTHENTICATION_REQUIRED", "Missing or invalid delegated bearer token."
        ),
        "Forbidden": _error_response(
            "FORBIDDEN", "Requester identity cannot access this operation."
        ),
        "InternalError": _error_response("INTERNAL_ERROR", "Unexpected safe failure."),
        "BackendUnavailable": _error_response(
            "BACKEND_UNAVAILABLE", "Attendance or audit dependency is unavailable."
        ),
        "NotFound": _error_response(
            "NOT_FOUND", "The requested attendance resource was not found."
        ),
    }


def protected_error_response_references(
    *, not_found: bool
) -> dict[str, dict[str, str]]:
    """Return per-operation references to shared safe-error components."""
    references = {
        "400": {"$ref": "#/components/responses/InvalidArgument"},
        "401": {"$ref": "#/components/responses/AuthenticationRequired"},
        "403": {"$ref": "#/components/responses/Forbidden"},
        "500": {"$ref": "#/components/responses/InternalError"},
        "503": {"$ref": "#/components/responses/BackendUnavailable"},
    }
    if not_found:
        references["404"] = {"$ref": "#/components/responses/NotFound"}
    return references


def security_error_schema() -> dict[str, object]:
    """Return the OpenAPI schema for the shared safe error envelope."""
    return SecurityErrorResponse.model_json_schema(mode="serialization")


def _error_response(code: SecurityErrorCode, description: str) -> dict[str, object]:
    """Return one safe error response declaration."""
    return {
        "description": description,
        "content": {
            "application/json": {
                "schema": {"$ref": "#/components/schemas/SecurityErrorResponse"},
                "example": SecurityErrorResponse(
                    code=code, message=SECURITY_ERROR_MESSAGES[code]
                ).model_dump(),
            }
        },
    }


_EVENT_EXAMPLE = {
    "attendance_event_id": 101,
    "employee_id": 42,
    "punch_type": "Office",
    "location": "Ljubljana",
    "checked_in_at": "2026-01-15T08:00:00+01:00",
    "checked_out_at": "2026-01-15T16:00:00+01:00",
    "note": None,
}
_DATE_RANGE_EXAMPLE = {"start_date": "2026-01-01", "end_date": "2026-01-15"}
_EMPLOYEE_EXAMPLE = {
    "employee_id": 42,
    "first_name": "Example",
    "last_name": "Employee",
    "username": "example.employee",
    "email": "example.employee@example.invalid",
    "active": 1,
}
_SUCCESS_EXAMPLES: dict[SuccessExample, object] = {
    "event_page": {
        "items": [_EVENT_EXAMPLE],
        "limit": 50,
        "offset": 0,
        "next_offset": None,
    },
    "event": _EVENT_EXAMPLE,
    "my_summary": {
        **_DATE_RANGE_EXAMPLE,
        "total_recorded_hours": "80.00",
        "attendance_day_count": 10,
        "monthly": [
            {"month": "2026-01", "recorded_hours": "80.00", "attendance_day_count": 10}
        ],
        "locations": [
            {
                "location": "Ljubljana",
                "recorded_hours": "80.00",
                "attendance_day_count": 10,
            }
        ],
    },
    "employee_page": {
        "items": [_EMPLOYEE_EXAMPLE],
        "limit": 50,
        "offset": 0,
        "next_offset": None,
    },
    "employee": _EMPLOYEE_EXAMPLE,
    "punch_types": [
        {
            "punch_type_id": 7,
            "punch_type": "Office",
            "active": 1,
            "derived_location_id": 3,
            "derived_location": "Ljubljana",
        }
    ],
    "locations": [{"location_id": 3, "location": "Ljubljana"}],
    "event_detail": {
        **_EVENT_EXAMPLE,
        "edited": False,
        "recorded_at": "2026-01-15T08:00:00+01:00",
        "modified_at": None,
        "modified_by": None,
        "data_source": "attendance",
    },
    "daily_attendance": {
        "employee_id": 42,
        "day": "2026-01-15",
        "events": [_EVENT_EXAMPLE],
        "logged_hours": "8.00",
        "known_planned_hours": "8.00",
        "balance_hours": "0.00",
        "planned_hours_complete": True,
        "incomplete_interval_count": 0,
        "anomaly_count": 0,
    },
    "planned_work": {
        **_DATE_RANGE_EXAMPLE,
        "employee_id": 42,
        "items": [{"day": "2026-01-15", "planned_hours": "8.00"}],
    },
    "current_attendance": {
        "items": [
            {
                "employee_id": 42,
                "first_name": "Example",
                "last_name": "Employee",
                "status": "office",
                "attendance_event_id": 101,
                "started_at": "2026-01-15T08:00:00+01:00",
                "punch_type": "Office",
                "location": "Ljubljana",
            }
        ],
        "as_of": "2026-01-15T12:00:00+01:00",
        "limit": 50,
        "offset": 0,
        "next_offset": None,
    },
    "employee_summary": {
        **_DATE_RANGE_EXAMPLE,
        "employee_id": 42,
        "logged_hours": "80.00",
        "known_planned_hours": "80.00",
        "balance_hours": "0.00",
        "planned_hours_complete": True,
        "punch_type_totals": [
            {"punch_type_id": 7, "punch_type": "Office", "hours": "80.00"}
        ],
        "incomplete_interval_count": 0,
        "anomaly_count": 0,
    },
    "employee_analysis": {
        **_DATE_RANGE_EXAMPLE,
        "employee_id": 42,
        "logged_hours": "80.00",
        "known_planned_hours": "80.00",
        "balance_hours": "0.00",
        "planned_hours_complete": True,
        "punch_type_totals": [
            {"punch_type_id": 7, "punch_type": "Office", "hours": "80.00"}
        ],
        "days": [
            {
                "day": "2026-01-15",
                "known_planned_hours": "8.00",
                "logged_hours": "8.00",
                "missing_attendance": False,
                "incomplete_interval_count": 0,
                "anomaly_count": 0,
            }
        ],
    },
    "organization_analysis": {
        **_DATE_RANGE_EXAMPLE,
        "active_employee_count": 1,
        "logged_hours": "80.00",
        "known_planned_hours": "80.00",
        "balance_hours": "0.00",
        "planned_hours_complete": True,
        "items": [
            {
                "employee_id": 42,
                "first_name": "Example",
                "last_name": "Employee",
                "logged_hours": "80.00",
                "known_planned_hours": "80.00",
                "balance_hours": "0.00",
                "planned_hours_complete": True,
                "incomplete_interval_count": 0,
                "anomaly_count": 0,
            }
        ],
        "limit": 50,
        "offset": 0,
        "next_offset": None,
    },
    "exceptions": {
        **_DATE_RANGE_EXAMPLE,
        "items": [
            {
                "employee_id": 42,
                "first_name": "Example",
                "last_name": "Employee",
                "day": "2026-01-15",
                "kind": "missing_attendance",
                "count": 1,
            }
        ],
        "limit": 50,
        "offset": 0,
        "next_offset": None,
    },
}
