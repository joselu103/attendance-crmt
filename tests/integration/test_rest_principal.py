"""Public transport seams for the shared, server-derived principal."""

import asyncio
from dataclasses import FrozenInstanceError, replace
from typing import Annotated

import httpx
import pytest
from fastapi import Depends

from attendance_crmt.audit import AuditEvent
from attendance_crmt.authentication import VerifiedDelegatedAccessToken
from attendance_crmt.identity import AuthenticatedTokenRequesterResolver, Principal
from attendance_crmt.rest import create_app, get_principal


class StaticTokenVerifier:
    """Return a token already verified by the authentication boundary."""

    def __init__(self, access_token: VerifiedDelegatedAccessToken | None) -> None:
        self._access_token = access_token

    async def verify_token(self, token: str) -> VerifiedDelegatedAccessToken | None:
        assert token == "delegated-token"
        return self._access_token


def _get(app, path: str, *, headers: list[tuple[str, str]]) -> httpx.Response:
    async def request() -> httpx.Response:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            return await client.get(path, headers=headers)

    return asyncio.run(request())


def _access_token() -> VerifiedDelegatedAccessToken:
    return VerifiedDelegatedAccessToken(
        token="delegated-token",
        client_id="22222222-2222-2222-2222-222222222222",
        scopes=["attendance.access"],
        claims={
            "tid": "11111111-1111-1111-1111-111111111111",
            "oid": "33333333-3333-3333-3333-333333333333",
            "preferred_username": "person@example.com",
            "roles": ["attendance.admin"],
        },
    )


def test_rest_dependency_resolves_an_immutable_principal(
    server_dependencies,
    employee_factory,
    audit_session_factory,
) -> None:
    employee = employee_factory.build(izvajalec_id=42, email="person@example.com")
    with server_dependencies.attendance_session_factory() as session:
        session.add(employee)
        session.commit()

    access_token = _access_token()
    resolver = AuthenticatedTokenRequesterResolver(
        session_factory=server_dependencies.attendance_session_factory,
        admin_role="attendance.admin",
    )
    app = create_app(
        replace(
            server_dependencies,
            auth_provider=StaticTokenVerifier(access_token),  # type: ignore[arg-type]
            principal_resolver=resolver,
        )
    )

    @app.get("/principal")
    async def principal_route(
        principal: Annotated[Principal, Depends(get_principal)],
    ) -> dict[str, object]:
        return {
            "actor_id": principal.actor_id,
            "employee_id": principal.employee_id,
            "roles": sorted(principal.roles),
            "client_id": principal.client_id,
            "auth_method": principal.auth_method,
        }

    response = _get(
        app,
        "/principal",
        headers=[
            ("Authorization", "Bearer delegated-token"),
            ("X-Correlation-ID", "11111111-1111-1111-1111-111111111111"),
        ],
    )

    assert response.status_code == 200
    assert response.json() == {
        "actor_id": "11111111-1111-1111-1111-111111111111:"
        "33333333-3333-3333-3333-333333333333",
        "employee_id": 42,
        "roles": ["admin", "employee"],
        "client_id": "22222222-2222-2222-2222-222222222222",
        "auth_method": "delegated_bearer",
    }
    with pytest.raises(FrozenInstanceError):
        resolver.resolve_access_token(access_token).employee_id = 99  # type: ignore[misc]
    with audit_session_factory() as session:
        events = session.query(AuditEvent).all()
    assert len(events) == 1
    assert events[0].tool_name == "rest:/principal"
    assert events[0].outcome == "success"


def test_rest_principal_dependency_rejects_duplicate_authorization_headers(
    server_dependencies,
) -> None:
    app = create_app(server_dependencies)

    @app.get("/principal")
    async def principal_route(
        principal: Annotated[Principal, Depends(get_principal)],
    ) -> dict[str, str]:
        return {"actor_id": principal.actor_id}

    response = _get(
        app,
        "/principal",
        headers=[
            ("Authorization", "Bearer delegated-token"),
            ("Authorization", "Bearer another-token"),
        ],
    )

    assert response.status_code == 401
    assert response.json() == {
        "code": "TOKEN_INVALID",
        "message": "Your sign-in could not be verified. Please try again.",
    }
