"""
GitHub webhook receiver.

POST /api/v1/webhooks/github

Security:
- HMAC-SHA256 signature verified before any processing.
- Idempotency enforced via X-GitHub-Delivery header.
- Accepts only workflow_run events (configurable in future phases).
"""
from __future__ import annotations

import json

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.observability.logging import get_logger
from app.observability.metrics import WEBHOOKS_DUPLICATE, WEBHOOKS_INVALID_SIGNATURE, WEBHOOKS_RECEIVED
from app.services.github.webhook_verifier import WebhookVerifier

router = APIRouter(tags=["webhooks"])
logger = get_logger(__name__)


@router.post(
    "/webhooks/github",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Receive GitHub webhook events",
)
async def receive_github_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    x_github_event: str | None = Header(default=None, alias="X-GitHub-Event"),
    x_github_delivery: str | None = Header(default=None, alias="X-GitHub-Delivery"),
    x_hub_signature_256: str | None = Header(default=None, alias="X-Hub-Signature-256"),
) -> dict:
    """
    Receive and queue a GitHub webhook event.

    Signature is verified synchronously.  All further processing is
    dispatched to a background worker so this endpoint returns fast.
    """
    if not x_github_delivery:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing X-GitHub-Delivery header",
        )

    raw_body = await request.body()

    # ------------------------------------------------------------------ #
    # 1. Verify signature — reject before any processing
    # ------------------------------------------------------------------ #
    verifier = WebhookVerifier()
    if not verifier.verify(raw_body, x_hub_signature_256):
        WEBHOOKS_INVALID_SIGNATURE.inc()
        logger.warning(
            "webhook_signature_invalid",
            delivery_id=x_github_delivery,
            event_type=x_github_event,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid webhook signature",
        )

    event_type = x_github_event or "unknown"
    WEBHOOKS_RECEIVED.labels(event_type=event_type).inc()

    # ------------------------------------------------------------------ #
    # 2. Check idempotency
    # ------------------------------------------------------------------ #
    from sqlalchemy import select
    from app.db.models.github import WebhookEvent

    existing = await db.execute(
        select(WebhookEvent).where(
            WebhookEvent.github_delivery_id == x_github_delivery
        )
    )
    if existing.scalar_one_or_none():
        WEBHOOKS_DUPLICATE.inc()
        logger.info(
            "webhook_duplicate_delivery_ignored",
            delivery_id=x_github_delivery,
        )
        return {"status": "duplicate", "delivery_id": x_github_delivery}

    # ------------------------------------------------------------------ #
    # 3. Persist the raw event
    # ------------------------------------------------------------------ #
    try:
        payload = json.loads(raw_body)
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid JSON payload",
        ) from exc

    action = payload.get("action")
    webhook_event = WebhookEvent(
        github_delivery_id=x_github_delivery,
        event_type=event_type,
        action=action,
        raw_payload=payload,
        processed=False,
    )
    db.add(webhook_event)
    await db.flush()

    logger.info(
        "webhook_received",
        delivery_id=x_github_delivery,
        event_type=event_type,
        action=action,
        event_id=str(webhook_event.id),
    )

    # ------------------------------------------------------------------ #
    # 4. Enqueue for background processing (Phase 2 will wire this up)
    # ------------------------------------------------------------------ #
    background_tasks.add_task(
        _enqueue_webhook_event,
        event_id=str(webhook_event.id),
        event_type=event_type,
        delivery_id=x_github_delivery,
    )

    return {
        "status": "accepted",
        "delivery_id": x_github_delivery,
        "event_id": str(webhook_event.id),
    }


async def _enqueue_webhook_event(
    event_id: str,
    event_type: str,
    delivery_id: str,
) -> None:
    """
    Push the event ID to the Redis webhook stream.
    Workers consume from this stream and do the heavy lifting.
    """
    import redis.asyncio as aioredis
    from app.config import get_settings

    settings = get_settings()
    redis_client = aioredis.from_url(
        str(settings.redis_url),
        decode_responses=True,
    )
    try:
        await redis_client.xadd(
            settings.redis_stream_webhooks,
            {
                "event_id": event_id,
                "event_type": event_type,
                "delivery_id": delivery_id,
            },
        )
        logger.info(
            "webhook_enqueued",
            event_id=event_id,
            event_type=event_type,
            delivery_id=delivery_id,
        )
    finally:
        await redis_client.aclose()
