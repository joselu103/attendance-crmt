import asyncio

import httpx

from attendance_crmt.authentication import EntraTokenVerifier
from attendance_crmt.dependencies import create_production_dependencies
from attendance_crmt.identity import AuthenticatedTokenRequesterResolver
from attendance_crmt.security_errors import AUTHENTICATION_REQUIRED_MESSAGE
from attendance_crmt.server import (
    create_production_http_app,
    create_production_server,
    create_server,
)
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
        dependencies.requester_resolver,
        AuthenticatedTokenRequesterResolver,
    )
    assert isinstance(dependencies.auth_provider, EntraTokenVerifier)
    assert dependencies.requester_resolver.email_aliases == {
        "entra-upn@example.onmicrosoft.com": "employee@example.com"
    }

    server = create_server(dependencies, settings=settings)

    assert server.auth is dependencies.auth_provider


def test_production_http_app_factory_builds_authenticated_contract_app(
    monkeypatch,
    tmp_path,
) -> None:
    settings = _production_test_settings(monkeypatch, tmp_path)

    app = create_production_http_app(settings)

    assert app is not None


def test_production_server_requires_bearer_authentication(
    monkeypatch,
    tmp_path,
) -> None:
    settings = _production_test_settings(monkeypatch, tmp_path)
    server = create_production_server(settings)
    assert isinstance(server.auth, EntraTokenVerifier)

    app = server.http_app(path="/mcp", stateless_http=True)

    async def request() -> httpx.Response:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            return await client.post("/mcp", json={})

    response = asyncio.run(request())

    assert response.status_code == 401
    assert response.json() == {
        "code": "AUTHENTICATION_REQUIRED",
        "message": AUTHENTICATION_REQUIRED_MESSAGE,
    }
