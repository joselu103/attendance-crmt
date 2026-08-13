"""Structured JSON logging powered by structlog."""

from __future__ import annotations

import logging
import sys
from typing import Any

import structlog


def configure_structlog() -> None:
    """Configure application event logs as newline-delimited JSON on stderr."""
    structlog.configure(
        processors=[
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(sort_keys=True),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> Any:
    """Return a structured application logger."""
    return structlog.get_logger(name)
