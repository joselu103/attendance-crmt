"""Black-box behavior for the REST application shell."""

import asyncio

import httpx
from starlette.types import ASGIApp

from attendance_crmt.audit import AuditEvent
from attendance_crmt.rest import create_app


class DependenciesThatMustNotBeAccessed:
    """Injected boundary dependencies that fail when the liveness path touches them."""

    def __getattribute__(self, name: str) -> object:
        raise AssertionError(f"Liveness must not access injected dependency: {name}")


def _get(app: ASGIApp, path: str) -> httpx.Response:
    async def request() -> httpx.Response:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            return await client.get(path)

    return asyncio.run(request())


def test_health_is_public_liveness() -> None:
    """The REST shell exposes the frozen liveness response."""
    response = _get(create_app(), "/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_does_not_create_a_durable_audit_event(
    server_dependencies, audit_session_factory
) -> None:
    """Public liveness has operational logging but no protected-operation audit."""
    response = _get(create_app(server_dependencies), "/health")

    assert response.status_code == 200
    with audit_session_factory() as session:
        assert session.query(AuditEvent).count() == 0


def test_health_does_not_access_injected_dependencies() -> None:
    """Liveness remains independent from SQL, Entra, and audit dependencies."""
    response = _get(
        create_app(dependencies=DependenciesThatMustNotBeAccessed()),
        "/health",
    )

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
