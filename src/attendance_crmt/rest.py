"""FastAPI REST application composition."""

from fastapi import FastAPI

from attendance_crmt.dependencies import ServerDependencies


def create_app(dependencies: ServerDependencies | None = None) -> FastAPI:
    """Create the REST shell from optional, explicitly injected dependencies."""
    app = FastAPI(openapi_url=None, docs_url=None, redoc_url=None)
    app.state.dependencies = dependencies

    @app.get("/health")
    async def health() -> dict[str, str]:
        """Report public process liveness without checking dependencies."""
        return {"status": "ok"}

    return app
