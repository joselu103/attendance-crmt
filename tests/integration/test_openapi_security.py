"""OpenAPI authorization metadata for the interactive REST documentation."""

from attendance_crmt.rest import (
    CORRELATION_ID_HEADER,
    DELEGATED_BEARER_SCHEME_NAME,
    create_app,
)


def test_openapi_describes_bearer_and_correlation_for_protected_routes() -> None:
    schema = create_app().openapi()

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
