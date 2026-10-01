import asyncio

import httpx

from attendance_crmt.authentication import EntraTokenVerifier
from attendance_crmt.dependencies import create_production_dependencies
from attendance_crmt.identity import AuthenticatedTokenRequesterResolver
from attendance_crmt.security_errors import AUTHENTICATION_REQUIRED_MESSAGE
from attendance_crmt.server import create_production_http_app
from attendance_crmt.settings import Settings


def _production_test_settings(monkeypatch, tmp_path) -> Settings:
    monkeypatch.setenv(
        "ATTENDANCE_AUDIT_DATABASE_PATH",
        str(tmp_path / "production-audit.sqlite3"),
    )
    return Settings(_env_file=None)


def test_production_dependencies_use_authenticated_requester(
    monkeypatch,
    tmp_path,
) -> None:
    monkeypatch.setenv(
        "ATTENDANCE_ENTRA_EMAIL_ALIASES",
        '{"entra-upn@example.onmicrosoft.com":"employee@example.com"}',
    )
    settings = _production_test_settings(monkeypatch, tmp_path)

    dependencies = create_production_dependencies(settings)

    assert isinstance(
        dependencies.principal_resolver,
        AuthenticatedTokenRequesterResolver,
    )
    assert isinstance(dependencies.auth_provider, EntraTokenVerifier)
    assert dependencies.principal_resolver.email_aliases == {
        "entra-upn@example.onmicrosoft.com": "employee@example.com"
    }


def test_production_http_app_factory_builds_authenticated_contract_app(
    monkeypatch,
    tmp_path,
) -> None:
    settings = _production_test_settings(monkeypatch, tmp_path)

    app = create_production_http_app(settings)

    assert app is not None


def test_production_runtime_composes_the_rest_protected_surface(
    monkeypatch,
    tmp_path,
) -> None:
    settings = _production_test_settings(monkeypatch, tmp_path)
    app = create_production_http_app(settings)

    async def request() -> httpx.Response:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            return await client.get(
                "/api/v1/me/attendance-events?start_date=2026-08-10&end_date=2026-08-10"
            )

    response = asyncio.run(request())

    assert response.status_code == 401
    assert response.json() == {
        "code": "AUTHENTICATION_REQUIRED",
        "message": AUTHENTICATION_REQUIRED_MESSAGE,
    }
    assert response.headers["X-Attendance-API-Contract-Version"] == "1.0.0"
    assert "X-Attendance-MCP-Contract-Version" not in response.headers


def test_production_runtime_has_no_embedded_mcp_compatibility_endpoint(
    monkeypatch,
    tmp_path,
) -> None:
    settings = _production_test_settings(monkeypatch, tmp_path)
    app = create_production_http_app(settings)

    async def request() -> httpx.Response:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            return await client.post("/mcp", json={})

    response = asyncio.run(request())

    assert response.status_code == 404
