"""
OpenTelemetry tracing setup.

Instruments FastAPI and SQLAlchemy automatically.
Only active when `otel_enabled = true` in settings.
"""
from __future__ import annotations

from app.config import get_settings
from app.observability.logging import get_logger

logger = get_logger(__name__)


def configure_tracing() -> None:
    """Initialise OTLP tracing if enabled.  Call once at startup."""
    settings = get_settings()

    if not settings.otel_enabled:
        logger.info("opentelemetry_tracing_disabled")
        return

    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
            OTLPSpanExporter,
        )
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        resource = Resource.create({"service.name": settings.app_name.lower().replace(" ", "-")})
        provider = TracerProvider(resource=resource)
        exporter = OTLPSpanExporter(endpoint=settings.otel_exporter_otlp_endpoint, insecure=True)
        provider.add_span_processor(BatchSpanProcessor(exporter))
        trace.set_tracer_provider(provider)

        FastAPIInstrumentor().instrument()
        SQLAlchemyInstrumentor().instrument()

        logger.info(
            "opentelemetry_tracing_enabled",
            endpoint=settings.otel_exporter_otlp_endpoint,
        )
    except ImportError as exc:
        logger.warning("opentelemetry_import_failed", error=str(exc))
