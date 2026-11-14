"""
Pytest configuration and shared fixtures.

Uses a test SQLite database so unit tests run without PostgreSQL.
For integration tests, set TEST_DATABASE_URL to a real PostgreSQL DSN.
"""
from __future__ import annotations

import os
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

# Set minimal test environment variables BEFORE importing app modules
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost:5432/test")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/1")
os.environ.setdefault("GITHUB_APP_ID", "12345")
os.environ.setdefault("GITHUB_APP_PRIVATE_KEY", "placeholder")
os.environ.setdefault("GITHUB_WEBHOOK_SECRET", "test_secret")
os.environ.setdefault("ENVIRONMENT", "testing")

# Configure logging before any test imports to avoid structlog crashes
from app.observability.logging import configure_logging  # noqa: E402
configure_logging()

from app.db.models import Base  # noqa: E402
from app.main import create_app  # noqa: E402


# In-memory SQLite database for unit tests
TEST_DB_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture(scope="function")
async def db_engine():
    """Create a fresh in-memory SQLite engine per test function."""
    engine = create_async_engine(TEST_DB_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def db_session(db_engine) -> AsyncGenerator[AsyncSession, None]:
    """Yield a test database session with automatic rollback."""
    factory = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture(scope="function")
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """
    Yield an HTTPX async test client.

    The database dependency is overridden to use the test session.
    """
    from app.db.session import get_db

    app = create_app()
    app.dependency_overrides[get_db] = lambda: db_session

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as c:
        yield c
