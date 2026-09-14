"""Environment-aware, safe structured logging powered by structlog."""

from __future__ import annotations

import logging
import sys
from collections.abc import Mapping
from typing import Any, Literal, TextIO

import structlog

LoggingEnvironment = Literal["development", "staging", "production"]

SENSITIVE_FIELD_NAMES = frozenset(
    {"authorization", "cookie", "password", "secret", "token"}
)


class _NamedPrintLoggerFactory:
    """Create output loggers that retain structlog's requested logger name."""

    def __init__(self, stream: TextIO) -> None:
        self._stream = stream

    def __call__(self, *args: Any) -> structlog.PrintLogger:
        logger = structlog.PrintLogger(self._stream)
        logger.name = str(args[0]) if args else "attendance_crmt"
        return logger


def redact_sensitive_fields(
    _logger: Any, _method_name: str, event_dict: Mapping[str, Any]
) -> dict[str, Any]:
    """Return an event copy with sensitive fields recursively redacted."""
    return _redact(event_dict)


def _redact(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            key: "[REDACTED]"
            if isinstance(key, str) and key.casefold() in SENSITIVE_FIELD_NAMES
            else _redact(item)
            for key, item in value.items()
        }
    if isinstance(value, list | tuple):
        return [_redact(item) for item in value]
    return value


def configure_structlog(
    environment: LoggingEnvironment = "development", *, stream: TextIO | None = None
) -> None:
    """Configure safe, environment-appropriate application event logs."""
    is_development = environment == "development"
    output = stream or sys.stdout
    structlog.configure(
        processors=[
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.stdlib.add_logger_name,
            structlog.processors.CallsiteParameterAdder(
                {
                    structlog.processors.CallsiteParameter.MODULE,
                    structlog.processors.CallsiteParameter.FILENAME,
                    structlog.processors.CallsiteParameter.LINENO,
                }
            ),
            redact_sensitive_fields,
            structlog.processors.format_exc_info,
            (
                structlog.dev.ConsoleRenderer(colors=True)
                if is_development
                else structlog.processors.JSONRenderer(sort_keys=True)
            ),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.DEBUG if is_development else logging.INFO
        ),
        logger_factory=_NamedPrintLoggerFactory(output),
        cache_logger_on_first_use=False,
    )


def get_logger(name: str) -> Any:
    """Return a structured application logger."""
    return structlog.get_logger(name)
