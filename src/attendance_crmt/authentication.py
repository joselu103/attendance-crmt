"""Entra token verification and safe MCP authentication transport behavior."""

import asyncio
import logging
from collections.abc import Callable, MutableMapping
from typing import Any, Protocol
from uuid import UUID

import httpx
import jwt
from fastmcp.server.auth import AccessToken, TokenVerifier
from jwt import InvalidTokenError, PyJWKClient, PyJWKClientError
from pydantic import (
    AnyHttpUrl,
    BaseModel,
    ConfigDict,
    ValidationError,
    field_validator,
    model_validator,
)
from starlette.middleware import Middleware
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from attendance_crmt.http_contract import (
    ContractVersionHeaderMiddleware,
    CorrelationIdMiddleware,
)
from attendance_crmt.observability import get_logger
from attendance_crmt.security_errors import (
    AUTHENTICATION_REQUIRED_MESSAGE,
    TOKEN_INVALID_MESSAGE,
    SecurityErrorResponse,
)
from attendance_crmt.settings import EntraMcpAuthenticationSettings

logger = logging.getLogger(__name__)
security_logger = get_logger(__name__)


def build_attendance_mcp_middleware(
    authentication_middleware: list[Middleware],
) -> list[Middleware]:
    """Wrap bearer authentication with Attendance's HTTP contract behavior."""
    return [
        Middleware(ContractVersionHeaderMiddleware),
        Middleware(AuthenticationErrorContractMiddleware),
        *authentication_middleware,
        Middleware(CorrelationIdMiddleware),
    ]


class OpenIdConfiguration(BaseModel):
    """OpenID provider values required by the resource server."""

    model_config = ConfigDict(frozen=True)

    issuer: AnyHttpUrl
    jwks_uri: AnyHttpUrl


class OpenIdConfigurationLoader(Protocol):
    """Load validated provider metadata for delegated-token verification."""

    async def load(self, url: str) -> OpenIdConfiguration:
        """Load and validate OpenID configuration from a trusted URL."""

        ...


class HttpOpenIdConfigurationLoader:
    """Load OpenID metadata over HTTP with bounded I/O and no redirects."""

    def __init__(self, *, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._transport = transport

    async def load(self, url: str) -> OpenIdConfiguration:
        async with httpx.AsyncClient(
            follow_redirects=False,
            timeout=httpx.Timeout(10.0),
            transport=self._transport,
        ) as client:
            response = await client.get(url, headers={"Accept": "application/json"})
            response.raise_for_status()
        return OpenIdConfiguration.model_validate(response.json())


class EntraDelegatedClaims(BaseModel):
    """Typed claims required to resolve an interactive Entra user safely."""

    model_config = ConfigDict(frozen=True, extra="allow")

    tid: UUID
    oid: UUID
    preferred_username: str
    scp: str
    azp: UUID | None = None
    appid: UUID | None = None
    idtyp: str | None = None
    exp: int
    roles: tuple[str, ...] = ()

    @field_validator("preferred_username", "scp")
    @classmethod
    def require_non_blank(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("claim must not be blank")
        return normalized

    @model_validator(mode="after")
    def require_delegated_client(self) -> EntraDelegatedClaims:
        """Reject application-only tokens and claims with no client identity."""
        if self.idtyp is not None and self.idtyp.casefold() == "app":
            raise ValueError("application-only tokens are not accepted")
        if self.azp is None and self.appid is None:
            raise ValueError("azp or appid claim is required")
        return self

    @property
    def client_id(self) -> UUID:
        """Return the delegated client ID, preferring the ``azp`` claim."""
        value = self.azp or self.appid
        if value is None:  # pragma: no cover - guarded by model validation
            raise ValueError("azp or appid claim is required")
        return value

    @property
    def scopes(self) -> list[str]:
        return self.scp.split()


JwkClientFactory = Callable[[str], PyJWKClient]


def _default_jwk_client_factory(uri: str) -> PyJWKClient:
    return PyJWKClient(
        uri,
        cache_keys=False,
        cache_jwk_set=True,
        lifespan=300,
        timeout=10,
    )


class EntraTokenVerifier(TokenVerifier):
    """Validate delegated Entra access tokens against tenant metadata and JWKS."""

    def __init__(
        self,
        settings: EntraMcpAuthenticationSettings,
        *,
        metadata_loader: OpenIdConfigurationLoader | None = None,
        jwk_client_factory: JwkClientFactory | None = None,
    ) -> None:
        super().__init__(
            base_url=str(settings.mcp_base_url),
            required_scopes=[settings.required_scope],
        )
        self._settings = settings
        self._metadata_loader = metadata_loader or HttpOpenIdConfigurationLoader()
        self._jwk_client_factory = jwk_client_factory or _default_jwk_client_factory
        self._jwk_client: PyJWKClient | None = None
        self._metadata_lock = asyncio.Lock()

    def get_middleware(self) -> list[Middleware]:
        """Add Attendance's version, error, and correlation HTTP contracts."""
        return build_attendance_mcp_middleware(super().get_middleware())

    async def verify_token(self, token: str) -> AccessToken | None:
        """Validate one delegated token and return ``None`` for safe rejection."""
        try:
            jwk_client = await self._get_jwk_client()
            signing_key = await asyncio.to_thread(
                jwk_client.get_signing_key_from_jwt,
                token,
            )
            decoded = jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256"],
                audience=self._settings.audience,
                issuer=str(self._settings.issuer),
                leeway=self._settings.clock_skew_seconds,
                options={
                    "require": ["iss", "aud", "exp", "nbf", "iat"],
                    "verify_signature": True,
                    "verify_exp": True,
                    "verify_nbf": True,
                    "verify_iat": True,
                    "verify_iss": True,
                    "verify_aud": True,
                    "strict_aud": True,
                },
            )
            if decoded.get("aud") != self._settings.audience:
                self._log_auth_failed("audience_mismatch")
                return None
            claims = EntraDelegatedClaims.model_validate(decoded)
            if claims.tid != self._settings.tenant_id:
                self._log_auth_failed("tenant_mismatch")
                return None
            if claims.client_id not in self._settings.allowed_client_ids:
                self._log_auth_failed("client_not_allowed")
                return None
            if self._settings.required_scope not in claims.scopes:
                self._log_auth_failed("scope_missing")
                return None
            subject = f"{claims.tid}:{claims.oid}"
            security_logger.info(
                "auth_validated",
                subject=subject,
                client_id=str(claims.client_id),
                authentication_scheme="bearer",
            )
            return AccessToken(
                token=token,
                client_id=str(claims.client_id),
                scopes=claims.scopes,
                expires_at=claims.exp,
                resource=self._settings.audience,
                subject=subject,
                claims=decoded,
            )
        except InvalidTokenError:
            self._log_auth_failed("token_validation_failed")
            return None
        except ValidationError:
            self._log_auth_failed("claim_contract_invalid")
            return None
        except PyJWKClientError:
            self._log_auth_failed("signing_key_unavailable")
            return None
        except httpx.HTTPError, TimeoutError:
            self._log_auth_failed("identity_metadata_unavailable")
            return None
        except ValueError:
            self._log_auth_failed("identity_configuration_invalid")
            return None
        except Exception:  # noqa: BLE001
            logger.error("Entra token validation infrastructure failed")
            self._log_auth_failed("unexpected_failure")
            return None

    @staticmethod
    def _log_auth_failed(reason: str) -> None:
        """Report a stable failure reason without retaining credential details."""
        security_logger.info(
            "auth_failed", reason=reason, authentication_scheme="bearer"
        )

    async def _get_jwk_client(self) -> PyJWKClient:
        """Initialize and cache a JWKS client after validating provider metadata."""
        if self._jwk_client is not None:
            return self._jwk_client

        async with self._metadata_lock:
            if self._jwk_client is not None:
                return self._jwk_client
            metadata = await self._metadata_loader.load(
                str(self._settings.openid_configuration_url)
            )
            if str(metadata.issuer) != str(self._settings.issuer):
                raise ValueError(
                    "OpenID metadata issuer does not match configured issuer"
                )
            if (
                self._settings.issuer.scheme == "https"
                and metadata.jwks_uri.scheme != "https"
            ):
                raise ValueError("JWKS URI must use HTTPS")
            self._jwk_client = self._jwk_client_factory(str(metadata.jwks_uri))
            return self._jwk_client


class AuthenticationErrorContractMiddleware:
    """Replace framework 401 bodies with the stable public security contract."""

    def __init__(self, app: ASGIApp) -> None:
        self._app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        rejected_start: MutableMapping[str, Any] | None = None

        async def send_with_contract(message: Message) -> None:
            nonlocal rejected_start

            if message["type"] == "http.response.start":
                if message["status"] != 401:
                    await send(message)
                    return
                rejected_start = message
                return

            if rejected_start is None:
                await send(message)
                return

            if message["type"] != "http.response.body" or message.get(
                "more_body", False
            ):
                return

            has_authorization = any(
                name.lower() == b"authorization" for name, _ in scope["headers"]
            )
            if has_authorization:
                response = SecurityErrorResponse(
                    code="TOKEN_INVALID",
                    message=TOKEN_INVALID_MESSAGE,
                )
            else:
                response = SecurityErrorResponse(
                    code="AUTHENTICATION_REQUIRED",
                    message=AUTHENTICATION_REQUIRED_MESSAGE,
                )
            body = response.model_dump_json().encode("utf-8")
            authenticate_headers = [
                (name, value)
                for name, value in rejected_start.get("headers", [])
                if name.lower() == b"www-authenticate"
            ]
            await send(
                {
                    "type": "http.response.start",
                    "status": 401,
                    "headers": [
                        *authenticate_headers,
                        (b"content-type", b"application/json"),
                        (b"content-length", str(len(body)).encode("ascii")),
                    ],
                }
            )
            await send({"type": "http.response.body", "body": body})

        await self._app(scope, receive, send_with_contract)
