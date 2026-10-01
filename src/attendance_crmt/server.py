"""Production REST application composition."""

from fastapi import FastAPI

from attendance_crmt.dependencies import create_production_dependencies
from attendance_crmt.observability import configure_structlog
from attendance_crmt.rest import create_app
from attendance_crmt.settings import Settings, get_settings


def create_production_http_app(settings: Settings | None = None) -> FastAPI:
    """Build the protected Attendance CRMT REST application."""
    settings = settings or get_settings()
    configure_structlog(settings.environment)
    return create_app(create_production_dependencies(settings))
