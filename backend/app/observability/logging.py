"""
Structured JSON logging via structlog.

Every log line emitted by the application includes:
- timestamp (ISO-8601 UTC)
- log level
- logger name
- correlation_id  (injected by middleware)
- additional context bound by callers

Uses stdlib logging as the underlying backend so that:
- `add_logger_name` works correctly
- Third-party libraries that use stdlib logging are captured
"""
from __future__ import annotations

import logging
import sys

import structlog

from app.config import Environment, get_settings

_configured = False


def configure_logging() -> None:
    """Call once at application startup."""
    global _configured
    if _configured:
        return
    _configured = True

    settings = get_settings()
    numeric_level = getattr(logging, settings.log_level.upper(), logging.INFO)

    # stdlib logging backend
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=numeric_level,
        force=True,
    )

    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
    ]

    if settings.environment == Environment.DEVELOPMENT or settings.environment == Environment.TESTING:
        renderer = structlog.dev.ConsoleRenderer()
    else:
        renderer = structlog.processors.JSONRenderer()

    structlog.configure(
        processors=shared_processors + [
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        processor=renderer,
        foreign_pre_chain=shared_processors,
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(numeric_level)


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Return a structlog logger bound to *name*."""
    return structlog.get_logger(name)
