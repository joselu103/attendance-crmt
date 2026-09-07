"""FastAPI REST application composition and protected-route identity seam."""

from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request
from fastmcp.server.auth import AccessToken

from attendance_crmt.dependencies import ServerDependencies
from attendance_crmt.identity import Principal
from attendance_crmt.security_errors import SecurityFailure


def _bearer_token(request: Request) -> str:
    """Read exactly one syntactically valid delegated bearer credential."""
    values = request.headers.getlist("authorization")
    if not values:
        raise SecurityFailure(code="AUTHENTICATION_REQUIRED")
    if len(values) != 1:
        raise SecurityFailure(code="TOKEN_INVALID")

    scheme, separator, credential = values[0].partition(" ")
    if scheme.casefold() != "bearer" or not separator or not credential.strip():
        raise SecurityFailure(code="TOKEN_INVALID")
    return credential.strip()


async def get_principal(request: Request) -> Principal:
    """FastAPI dependency that verifies a bearer and derives one Principal."""
    dependencies: ServerDependencies | None = request.app.state.dependencies
    if dependencies is None or dependencies.auth_provider is None:
        raise SecurityFailure(code="TOKEN_INVALID")
    if dependencies.principal_resolver is None:
        raise SecurityFailure(code="TOKEN_INVALID")

    verifier: Callable[[str], Awaitable[AccessToken | None]] = (
        dependencies.auth_provider.verify_token
    )
    access_token = await verifier(_bearer_token(request))
    return dependencies.principal_resolver.resolve_access_token(access_token)


def create_app(dependencies: ServerDependencies | None = None) -> FastAPI:
    """Create the REST shell from optional, explicitly injected dependencies."""
    app = FastAPI(openapi_url=None, docs_url=None, redoc_url=None)
    app.state.dependencies = dependencies

    @app.get("/health")
    async def health() -> dict[str, str]:
        """Report public process liveness without checking dependencies."""
        return {"status": "ok"}

    return app
