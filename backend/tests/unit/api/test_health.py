"""
Unit tests for the health and readiness endpoints.
"""
from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health_returns_200(client: AsyncClient) -> None:
    """Liveness endpoint must return 200 and status='ok'."""
    response = await client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "version" in data


@pytest.mark.asyncio
async def test_health_includes_version(client: AsyncClient) -> None:
    response = await client.get("/api/v1/health")
    assert response.json()["version"] == "0.1.0"


@pytest.mark.asyncio
async def test_metrics_endpoint_available(client: AsyncClient) -> None:
    """Prometheus metrics endpoint must be reachable."""
    response = await client.get("/metrics", follow_redirects=True)
    # Prometheus ASGI returns 200 with text/plain content
    assert response.status_code == 200
