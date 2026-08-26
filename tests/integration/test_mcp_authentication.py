import asyncio
import json
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import UUID

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastmcp import FastMCP
from fastmcp.server.auth import TokenVerifier
from jwt import PyJWKClient
from jwt.algorithms import RSAAlgorithm
from pydantic import AnyHttpUrl
from starlette.middleware import Middleware

from attendance_crmt.authentication import (
    AuthenticationErrorContractMiddleware,
    EntraTokenVerifier,
    HttpOpenIdConfigurationLoader,
    OpenIdConfiguration,
)
from attendance_crmt.settings import EntraMcpAuthenticationSettings

TENANT_ID = UUID("11111111-1111-1111-1111-111111111111")
CLIENT_ID = UUID("22222222-2222-2222-2222-222222222222")
USER_ID = UUID("33333333-3333-3333-3333-333333333333")
OMIT = object()


class RejectAllTokenVerifier(TokenVerifier):
    async def verify_token(self, token: str):
        return None

    def get_middleware(self) -> list[Middleware]:
        return [
            Middleware(AuthenticationErrorContractMiddleware),
            *super().get_middleware(),
        ]


class StaticOpenIdConfigurationLoader:
    def __init__(self, configuration: OpenIdConfiguration) -> None:
        self._configuration = configuration

    async def load(self, url: str) -> OpenIdConfiguration:
        return self._configuration


class StaticJwksClient(PyJWKClient):
    def __init__(self, provider: Callable[[], dict[str, Any]]) -> None:
        super().__init__("https://login.microsoftonline.test/keys")
        self._provider = provider

    def fetch_data(self) -> dict[str, Any]:
        jwks = self._provider()
        if self.jwk_set_cache is not None:
            self.jwk_set_cache.put(cast(Any, jwks))
        return jwks


def _authentication_settings() -> EntraMcpAuthenticationSettings:
    return EntraMcpAuthenticationSettings(
        mcp_base_url=AnyHttpUrl("http://test"),
        tenant_id=TENANT_ID,
        issuer=AnyHttpUrl(f"https://login.microsoftonline.com/{TENANT_ID}/v2.0"),
        openid_configuration_url=AnyHttpUrl(
            f"https://login.microsoftonline.com/{TENANT_ID}/v2.0/"
            ".well-known/openid-configuration"
        ),
        audience="api://attendance-crmt-test",
        allowed_client_ids=frozenset({CLIENT_ID}),
        required_scope="attendance.access",
        clock_skew_seconds=60,
        admin_role="attendance.admin",
    )


def _jwk(private_key, *, kid: str) -> dict[str, Any]:
    value = json.loads(RSAAlgorithm.to_jwk(private_key.public_key()))
    value.update({"kid": kid, "use": "sig", "alg": "RS256"})
    return value


def _signed_token(
    private_key,
    settings: EntraMcpAuthenticationSettings,
    *,
    kid: str = "key-1",
    overrides: dict[str, object] | None = None,
) -> str:
    now = datetime.now(UTC)
    claims: dict[str, object] = {
        "iss": str(settings.issuer),
        "aud": settings.audience,
        "exp": now + timedelta(minutes=5),
        "nbf": now - timedelta(seconds=5),
        "iat": now - timedelta(seconds=5),
        "tid": str(settings.tenant_id),
        "oid": str(USER_ID),
        "preferred_username": "person@example.com",
        "azp": str(CLIENT_ID),
        "scp": "openid attendance.access",
        "roles": ["attendance.admin"],
    }
    for name, value in (overrides or {}).items():
        if value is OMIT:
            claims.pop(name, None)
        else:
            claims[name] = value
    return jwt.encode(claims, private_key, algorithm="RS256", headers={"kid": kid})


def _verifier(
    settings: EntraMcpAuthenticationSettings,
    jwks_provider: Callable[[], dict[str, Any]],
) -> EntraTokenVerifier:
    configuration = OpenIdConfiguration(
        issuer=settings.issuer,
        jwks_uri="https://login.microsoftonline.test/keys",
    )
    return EntraTokenVerifier(
        settings,
        metadata_loader=StaticOpenIdConfigurationLoader(configuration),
        jwk_client_factory=lambda _: StaticJwksClient(jwks_provider),
    )


def _post_mcp(app, *, authorization: str | None = None) -> httpx.Response:
    async def request() -> httpx.Response:
        headers = {"Authorization": authorization} if authorization else {}
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            return await client.post("/mcp", headers=headers, json={})

    return asyncio.run(request())


def test_missing_token_returns_authentication_required() -> None:
    verifier = RejectAllTokenVerifier(base_url="http://test")
    server = FastMCP("authentication-test", auth=verifier)
    app = server.http_app(path="/mcp", stateless_http=True)

    response = _post_mcp(app)

    assert response.status_code == 401
    assert response.json() == {
        "code": "AUTHENTICATION_REQUIRED",
        "message": "Please sign in to use Attendance.",
    }


def test_valid_delegated_token_returns_typed_access_token() -> None:
    settings = _authentication_settings()
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    token = _signed_token(private_key, settings)
    verifier = _verifier(settings, lambda: {"keys": [_jwk(private_key, kid="key-1")]})

    access_token = asyncio.run(verifier.verify_token(token))

    assert access_token is not None
    assert access_token.client_id == str(CLIENT_ID)
    assert access_token.subject == f"{TENANT_ID}:{USER_ID}"
    assert access_token.scopes == ["openid", "attendance.access"]
    assert access_token.claims["preferred_username"] == "person@example.com"


@pytest.mark.parametrize(
    "overrides",
    [
        {"exp": datetime.now(UTC) - timedelta(seconds=30)},
        {"nbf": datetime.now(UTC) + timedelta(seconds=30)},
        {"iat": datetime.now(UTC) + timedelta(seconds=30)},
    ],
)
def test_clock_skew_accepts_temporal_claims_within_configured_allowance(
    overrides: dict[str, object],
) -> None:
    settings = _authentication_settings()
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    verifier = _verifier(settings, lambda: {"keys": [_jwk(private_key, kid="key-1")]})
    token = _signed_token(private_key, settings, overrides=overrides)

    assert asyncio.run(verifier.verify_token(token)) is not None


def test_http_openid_loader_parses_tenant_metadata_without_redirects() -> None:
    settings = _authentication_settings()

    def handle(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == str(settings.openid_configuration_url)
        assert request.headers["accept"] == "application/json"
        return httpx.Response(
            200,
            json={
                "issuer": str(settings.issuer),
                "jwks_uri": "https://login.microsoftonline.test/keys",
            },
        )

    loader = HttpOpenIdConfigurationLoader(transport=httpx.MockTransport(handle))

    configuration = asyncio.run(loader.load(str(settings.openid_configuration_url)))

    assert configuration.issuer == settings.issuer
    assert str(configuration.jwks_uri) == "https://login.microsoftonline.test/keys"


def test_metadata_issuer_mismatch_fails_closed() -> None:
    settings = _authentication_settings()
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    token = _signed_token(private_key, settings)
    configuration = OpenIdConfiguration(
        issuer=AnyHttpUrl("https://issuer.example.com/v2.0"),
        jwks_uri=AnyHttpUrl("https://login.microsoftonline.test/keys"),
    )
    verifier = EntraTokenVerifier(
        settings,
        metadata_loader=StaticOpenIdConfigurationLoader(configuration),
        jwk_client_factory=lambda _: StaticJwksClient(
            lambda: {"keys": [_jwk(private_key, kid="key-1")]}
        ),
    )

    assert asyncio.run(verifier.verify_token(token)) is None


def test_jwks_timeout_fails_closed() -> None:
    settings = _authentication_settings()
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    token = _signed_token(private_key, settings)

    def unavailable_jwks() -> dict[str, Any]:
        raise TimeoutError("simulated JWKS timeout")

    verifier = _verifier(settings, unavailable_jwks)

    assert asyncio.run(verifier.verify_token(token)) is None


@pytest.mark.parametrize(
    "case,overrides",
    [
        ("expired", {"exp": datetime.now(UTC) - timedelta(minutes=5)}),
        ("wrong audience", {"aud": "api://wrong-resource"}),
        (
            "multiple audiences",
            {"aud": ["api://attendance-crmt-test", "api://other-resource"]},
        ),
        (
            "wrong tenant",
            {"tid": "99999999-9999-9999-9999-999999999999"},
        ),
        (
            "app-only",
            {
                "scp": OMIT,
                "oid": OMIT,
                "preferred_username": OMIT,
                "roles": ["attendance.application"],
            },
        ),
        ("app-only marker", {"idtyp": "app"}),
        ("wrong issuer", {"iss": "https://issuer.example.com/v2.0"}),
        ("missing oid", {"oid": OMIT}),
        ("missing username", {"preferred_username": OMIT}),
        ("missing required scope", {"scp": "openid profile"}),
        (
            "unapproved client",
            {"azp": "88888888-8888-8888-8888-888888888888"},
        ),
        ("future not-before", {"nbf": datetime.now(UTC) + timedelta(minutes=5)}),
        ("future issued-at", {"iat": datetime.now(UTC) + timedelta(minutes=5)}),
    ],
    ids=lambda value: value if isinstance(value, str) else None,
)
def test_invalid_delegated_token_returns_token_invalid(
    case: str,
    overrides: dict[str, object],
) -> None:
    settings = _authentication_settings()
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    token = _signed_token(private_key, settings, overrides=overrides)
    verifier = _verifier(settings, lambda: {"keys": [_jwk(private_key, kid="key-1")]})
    app = FastMCP("authentication-test", auth=verifier).http_app(
        path="/mcp", stateless_http=True
    )

    response = _post_mcp(app, authorization=f"Bearer {token}")

    assert case
    assert response.status_code == 401
    assert response.json() == {
        "code": "TOKEN_INVALID",
        "message": "Your sign-in could not be verified. Please try again.",
    }


def test_malformed_token_returns_token_invalid() -> None:
    settings = _authentication_settings()
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    verifier = _verifier(settings, lambda: {"keys": [_jwk(private_key, kid="key-1")]})
    app = FastMCP("authentication-test", auth=verifier).http_app(
        path="/mcp", stateless_http=True
    )

    response = _post_mcp(app, authorization="Bearer not-a-jwt")

    assert response.status_code == 401
    assert response.json()["code"] == "TOKEN_INVALID"


def test_wrong_signature_returns_token_invalid() -> None:
    settings = _authentication_settings()
    trusted_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    attacker_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    token = _signed_token(attacker_key, settings)
    verifier = _verifier(settings, lambda: {"keys": [_jwk(trusted_key, kid="key-1")]})
    app = FastMCP("authentication-test", auth=verifier).http_app(
        path="/mcp", stateless_http=True
    )

    response = _post_mcp(app, authorization=f"Bearer {token}")

    assert response.status_code == 401
    assert response.json()["code"] == "TOKEN_INVALID"


def test_jwks_refresh_accepts_rotated_signing_key() -> None:
    settings = _authentication_settings()
    first_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    second_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    current_jwks = {"keys": [_jwk(first_key, kid="key-1")]}
    verifier = _verifier(settings, lambda: current_jwks)

    first_result = asyncio.run(
        verifier.verify_token(_signed_token(first_key, settings, kid="key-1"))
    )
    current_jwks = {"keys": [_jwk(second_key, kid="key-2")]}
    second_result = asyncio.run(
        verifier.verify_token(_signed_token(second_key, settings, kid="key-2"))
    )

    assert first_result is not None
    assert second_result is not None
