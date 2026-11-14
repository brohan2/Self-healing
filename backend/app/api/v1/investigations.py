"""
Investigation management endpoints.

GET  /api/v1/investigations        – list investigations
GET  /api/v1/investigations/{id}   – get investigation details
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.investigation import Investigation
from app.db.session import get_db

router = APIRouter(tags=["investigations"])


class InvestigationSummary(BaseModel):
    id: uuid.UUID
    workflow_run_id: uuid.UUID
    status: str
    failure_category: str | None
    error_summary: str | None
    confidence: float | None

    model_config = {"from_attributes": True}


class InvestigationDetail(InvestigationSummary):
    result: dict | None
    suspected_files: list | None


@router.get(
    "/investigations",
    response_model=list[InvestigationSummary],
    summary="List all investigations",
)
async def list_investigations(
    db: AsyncSession = Depends(get_db),
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[InvestigationSummary]:
    result = await db.execute(
        select(Investigation).order_by(Investigation.created_at.desc()).limit(limit).offset(offset)
    )
    investigations = result.scalars().all()
    return [InvestigationSummary.model_validate(inv) for inv in investigations]


@router.get(
    "/investigations/{investigation_id}",
    response_model=InvestigationDetail,
    summary="Get investigation details",
)
async def get_investigation(
    investigation_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> InvestigationDetail:
    result = await db.execute(
        select(Investigation).where(Investigation.id == investigation_id)
    )
    investigation = result.scalar_one_or_none()
    if not investigation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Investigation not found",
        )
    return InvestigationDetail.model_validate(investigation)
