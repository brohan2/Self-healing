"""
Unit tests for the webhook receiver endpoint.

Tests cover:
- Signature verification (valid / invalid / missing)
- Idempotency (duplicate delivery rejection)
- Payload persistence
"""
from __future__ import annotations

import hashlib
import hmac
import json

import pytest
from httpx import AsyncClient

WEBHOOK_SECRET = "test_secret"
VALID_PAYLOAD = {
    "action": "completed",
    "workflow_run": {
        "id": 123456789,
        "run_number": 1,
        "name": "CI",
        "head_sha": "abc123",
        "head_branch": "main",
        "status": "completed",
        "conclusion": "failure",
    },
    "repository": {
        "id": 987654321,
        "full_name": "org/repo",
    },
}


def _sign(payload: bytes, secret: str = WEBHOOK_SECRET) -> str:
    sig = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    return f"sha256={sig}"


@pytest.mark.asyncio
async def test_webhook_accepted_with_valid_signature(client: AsyncClient) -> None:
    payload = json.dumps(VALID_PAYLOAD).encode()
    response = await client.post(
        "/api/v1/webhooks/github",
        content=payload,
        headers={
            "Content-Type": "application/json",
            "X-GitHub-Event": "workflow_run",
            "X-GitHub-Delivery": "delivery-001",
            "X-Hub-Signature-256": _sign(payload),
        },
    )
    assert response.status_code == 202
    data = response.json()
    assert data["status"] == "accepted"
    assert data["delivery_id"] == "delivery-001"
    assert "event_id" in data


@pytest.mark.asyncio
async def test_webhook_rejected_with_invalid_signature(client: AsyncClient) -> None:
    payload = json.dumps(VALID_PAYLOAD).encode()
    response = await client.post(
        "/api/v1/webhooks/github",
        content=payload,
        headers={
            "Content-Type": "application/json",
            "X-GitHub-Event": "workflow_run",
            "X-GitHub-Delivery": "delivery-002",
            "X-Hub-Signature-256": "sha256=invalidsignature",
        },
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_webhook_rejected_with_missing_signature(client: AsyncClient) -> None:
    payload = json.dumps(VALID_PAYLOAD).encode()
    response = await client.post(
        "/api/v1/webhooks/github",
        content=payload,
        headers={
            "Content-Type": "application/json",
            "X-GitHub-Event": "workflow_run",
            "X-GitHub-Delivery": "delivery-003",
            # No X-Hub-Signature-256
        },
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_webhook_rejected_with_missing_delivery_id(client: AsyncClient) -> None:
    payload = json.dumps(VALID_PAYLOAD).encode()
    response = await client.post(
        "/api/v1/webhooks/github",
        content=payload,
        headers={
            "Content-Type": "application/json",
            "X-GitHub-Event": "workflow_run",
            "X-Hub-Signature-256": _sign(payload),
            # No X-GitHub-Delivery
        },
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_webhook_duplicate_delivery_returns_duplicate_status(
    client: AsyncClient,
) -> None:
    """Sending the same delivery ID twice must not create a duplicate record."""
    payload = json.dumps(VALID_PAYLOAD).encode()
    headers = {
        "Content-Type": "application/json",
        "X-GitHub-Event": "workflow_run",
        "X-GitHub-Delivery": "delivery-idempotent-001",
        "X-Hub-Signature-256": _sign(payload),
    }

    first = await client.post("/api/v1/webhooks/github", content=payload, headers=headers)
    assert first.status_code == 202
    assert first.json()["status"] == "accepted"

    second = await client.post("/api/v1/webhooks/github", content=payload, headers=headers)
    assert second.status_code == 202
    assert second.json()["status"] == "duplicate"


@pytest.mark.asyncio
async def test_webhook_correlation_id_in_response(client: AsyncClient) -> None:
    """Response must echo back a correlation ID header."""
    payload = json.dumps(VALID_PAYLOAD).encode()
    response = await client.post(
        "/api/v1/webhooks/github",
        content=payload,
        headers={
            "Content-Type": "application/json",
            "X-GitHub-Event": "workflow_run",
            "X-GitHub-Delivery": "delivery-corr-001",
            "X-Hub-Signature-256": _sign(payload),
            "X-Correlation-ID": "my-trace-id-123",
        },
    )
    assert response.headers.get("X-Correlation-ID") == "my-trace-id-123"
