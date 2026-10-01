"""Entra delegated-token verification for protected REST operations."""

import asyncio
import logging
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Protocol
from uuid import UUID

import httpx
import jwt
from jwt import InvalidTokenError, PyJWKClient, PyJWKClientError
from pydantic import (
    AnyHttpUrl,
    BaseModel,
    ConfigDict,
    ValidationError,
    field_validator,
    model_validator,
)

from attendance_crmt.observability import get_logger
from attendance_crmt.settings import EntraAuthenticationSettings

logger = logging.getLogger(__name__)
security_logger = get_logger(__name__)


@dataclass(frozen=True)
class VerifiedDelegatedAccessToken:
    """Trusted delegated-token facts consumed by the REST identity boundary."""

    client_id: str
    claims: Mapping[str, Any]
    token: str | None = None
    scopes: tuple[str, ...] = ()


class DelegatedTokenVerifier(Protocol):
    """Verify a raw bearer credential into trusted delegated-token facts."""

    async def verify_token(self, token: str) -> VerifiedDelegatedAccessToken | None:
        """Return verified facts, or ``None`` for a safe credential rejection."""

        ...


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


class EntraTokenVerifier:
    """Validate delegated Entra access tokens against tenant metadata and JWKS."""

    def __init__(
        self,
        settings: EntraAuthenticationSettings,
        *,
        metadata_loader: OpenIdConfigurationLoader | None = None,
        jwk_client_factory: JwkClientFactory | None = None,
    ) -> None:
        self._settings = settings
        self._metadata_loader = metadata_loader or HttpOpenIdConfigurationLoader()
        self._jwk_client_factory = jwk_client_factory or _default_jwk_client_factory
        self._jwk_client: PyJWKClient | None = None
        self._metadata_lock = asyncio.Lock()

    async def verify_token(self, token: str) -> VerifiedDelegatedAccessToken | None:
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
            return VerifiedDelegatedAccessToken(
                client_id=str(claims.client_id),
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
