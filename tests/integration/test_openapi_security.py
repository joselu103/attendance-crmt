"""OpenAPI authorization metadata for the interactive REST documentation."""

from attendance_crmt.rest import (
    CORRELATION_ID_HEADER,
    DELEGATED_BEARER_SCHEME_NAME,
    create_app,
)


def test_openapi_describes_bearer_and_correlation_for_protected_routes() -> None:
    schema = create_app().openapi()

    assert schema["info"]["version"] == "1.0.0"
    assert schema["components"]["securitySchemes"][DELEGATED_BEARER_SCHEME_NAME] == {
        "type": "http",
        "description": "Delegated Attendance Entra access token.",
        "scheme": "bearer",
        "bearerFormat": "JWT",
    }
    operation = schema["paths"]["/api/v1/me/attendance-events"]["get"]
    assert operation["security"] == [{DELEGATED_BEARER_SCHEME_NAME: []}]
    assert operation["parameters"][-1] == {
        "$ref": "#/components/parameters/CorrelationId"
    }
    assert schema["components"]["parameters"]["CorrelationId"] == {
        "name": CORRELATION_ID_HEADER,
        "in": "header",
        "required": True,
        "description": "A UUID that correlates this request with its audit outcome.",
        "schema": {"type": "string", "format": "uuid"},
    }


def test_openapi_keeps_health_public() -> None:
    operation = create_app().openapi()["paths"]["/health"]["get"]

    assert "security" not in operation
    assert not any(
        parameter.get("$ref") == "#/components/parameters/CorrelationId"
        for parameter in operation.get("parameters", [])
    )


def test_openapi_documents_concrete_response_schemas_and_safe_examples() -> None:
    schema = create_app().openapi()

    expected_schemas = {
        "/api/v1/me/attendance-events": "AttendanceEventPage",
        "/api/v1/me/attendance-events/latest": "AttendanceEventSummary",
        "/api/v1/me/attendance-summary": "MyAttendanceSummary",
        "/api/v1/employees": "EmployeePage",
        "/api/v1/employees/resolve": "EmployeeSummary",
        "/api/v1/employees/{employee_id}": "EmployeeSummary",
        "/api/v1/attendance-events/{attendance_event_id}": "AttendanceEventDetail",
        "/api/v1/employees/{employee_id}/attendance-events": "AttendanceEventPage",
        "/api/v1/employees/{employee_id}/daily-attendance": "DailyAttendance",
        "/api/v1/employees/{employee_id}/planned-work": "PlannedWorkResult",
        "/api/v1/attendance/current": "CurrentAttendancePage",
        "/api/v1/attendance/current-status": "CurrentWorkStatusPage",
        "/api/v1/employees/{employee_id}/attendance-summary": "EmployeeAttendanceSummary",
        "/api/v1/employees/{employee_id}/attendance-analysis": "EmployeeAttendanceAnalysis",
        "/api/v1/attendance/organization-analysis": "OrganizationAttendanceAnalysis",
        "/api/v1/attendance/exceptions": "AttendanceExceptionsPage",
    }

    for path, model in expected_schemas.items():
        responses = schema["paths"][path]["get"]["responses"]
        assert responses["200"]["content"]["application/json"]["schema"] == {
            "$ref": f"#/components/schemas/{model}"
        }
        assert responses["200"]["content"]["application/json"]["example"]
        assert "422" not in responses
        assert responses["400"] == {"$ref": "#/components/responses/InvalidArgument"}
        assert responses["401"] == {
            "$ref": "#/components/responses/AuthenticationRequired"
        }
        assert responses["403"] == {"$ref": "#/components/responses/Forbidden"}
        assert responses["500"] == {"$ref": "#/components/responses/InternalError"}
        assert responses["503"] == {"$ref": "#/components/responses/BackendUnavailable"}

    for path in (
        "/api/v1/me/attendance-events/latest",
        "/api/v1/employees/resolve",
        "/api/v1/employees/{employee_id}",
        "/api/v1/attendance-events/{attendance_event_id}",
    ):
        assert schema["paths"][path]["get"]["responses"]["404"] == {
            "$ref": "#/components/responses/NotFound"
        }

    for response in schema["components"]["responses"].values():
        assert response["content"]["application/json"]["schema"] == {
            "$ref": "#/components/schemas/SecurityErrorResponse"
        }
        assert response["content"]["application/json"]["example"]

    assert schema["paths"]["/api/v1/punch-types"]["get"]["responses"]["200"]["content"][
        "application/json"
    ]["schema"]["items"] == {"$ref": "#/components/schemas/PunchTypeSummary"}
    assert schema["paths"]["/api/v1/locations"]["get"]["responses"]["200"]["content"][
        "application/json"
    ]["schema"]["items"] == {"$ref": "#/components/schemas/LocationSummary"}
    assert schema["paths"]["/health"]["get"]["responses"]["200"]["content"][
        "application/json"
    ]["schema"] == {"$ref": "#/components/schemas/HealthResponse"}

    for path_item in schema["paths"].values():
        operation = path_item.get("get")
        if operation is None or "security" not in operation:
            continue
        responses = operation["responses"]
        assert "422" not in responses
        assert all(str(status) in responses for status in (400, 401, 403, 500, 503))
