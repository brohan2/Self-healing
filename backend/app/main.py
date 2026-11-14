"""
AutoFix AI – FastAPI application factory.

Create the app with `create_app()` so it can be imported in tests
without side effects.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import make_asgi_app

from app.api.middleware.correlation import CorrelationIDMiddleware
from app.api.middleware.logging import RequestLoggingMiddleware
from app.api.v1 import health, investigations, repositories, webhooks
from app.config import get_settings
from app.db.session import close_engine
from app.dependencies import close_redis_pool
from app.observability.logging import configure_logging, get_logger
from app.observability.tracing import configure_tracing


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Startup and shutdown lifecycle."""
    logger = get_logger(__name__)
    settings = get_settings()

    logger.info(
        "application_starting",
        name=settings.app_name,
        environment=settings.environment,
        version="0.1.0",
    )

    # Observability
    configure_tracing()

    # Start background workers
    from app.workers.manager import start_workers, stop_workers
    await start_workers()

    yield  # application runs here

    # Cleanup
    await stop_workers()
    await close_engine()
    await close_redis_pool()
    logger.info("application_stopped")


def create_app() -> FastAPI:
    """
    Build and return the FastAPI application.

    Call this function once at module level for production,
    or in fixtures for testing.
    """
    configure_logging()
    settings = get_settings()

    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        description="Autonomous GitHub Actions failure detection, debugging & code repair platform",
        docs_url="/docs" if settings.debug else None,
        redoc_url="/redoc" if settings.debug else None,
        openapi_url="/openapi.json" if settings.debug else None,
        lifespan=lifespan,
    )

    # ------------------------------------------------------------------ #
    # Middleware (registered in reverse order — last added runs first)
    # ------------------------------------------------------------------ #
    app.add_middleware(RequestLoggingMiddleware)
    app.add_middleware(CorrelationIDMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ------------------------------------------------------------------ #
    # Routers
    # ------------------------------------------------------------------ #
    prefix = settings.api_v1_prefix
    app.include_router(health.router, prefix=prefix)
    app.include_router(webhooks.router, prefix=prefix)
    app.include_router(investigations.router, prefix=prefix)
    app.include_router(repositories.router, prefix=prefix)

    # ------------------------------------------------------------------ #
    # Prometheus metrics endpoint
    # ------------------------------------------------------------------ #
    if settings.prometheus_enabled:
        metrics_app = make_asgi_app()
        app.mount("/metrics", metrics_app)

    return app


# Module-level app instance used by uvicorn
app = create_app()
