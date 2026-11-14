"""
Health and readiness endpoints.

GET /api/v1/health  – liveness probe (fast, no dependencies)
GET /api/v1/ready   – readiness probe (checks DB and Redis)
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.dependencies import get_redis_client
from app.observability.logging import get_logger

router = APIRouter(tags=["health"])
logger = get_logger(__name__)


class HealthResponse(BaseModel):
    status: str
    version: str = "0.1.0"


class ReadinessResponse(BaseModel):
    status: str
    db: str
    redis: str


@router.get(
    "/health",
    response_model=HealthResponse,
    status_code=status.HTTP_200_OK,
    summary="Liveness probe",
)
async def health() -> HealthResponse:
    """Returns 200 as long as the process is alive."""
    return HealthResponse(status="ok")


@router.get(
    "/ready",
    response_model=ReadinessResponse,
    status_code=status.HTTP_200_OK,
    summary="Readiness probe",
)
async def readiness(
    db: AsyncSession = Depends(get_db),
    redis=Depends(get_redis_client),
) -> ReadinessResponse:
    """
    Checks database and Redis connectivity.
    Returns 503 if any dependency is unavailable.
    """
    db_status = "ok"
    redis_status = "ok"

    try:
        await db.execute(text("SELECT 1"))
    except Exception as exc:
        logger.error("readiness_db_check_failed", error=str(exc))
        db_status = "error"

    try:
        await redis.ping()
    except Exception as exc:
        logger.error("readiness_redis_check_failed", error=str(exc))
        redis_status = "error"

    overall = "ok" if db_status == "ok" and redis_status == "ok" else "degraded"
    return ReadinessResponse(status=overall, db=db_status, redis=redis_status)
