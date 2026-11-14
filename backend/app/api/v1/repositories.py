"""
Repository settings endpoints.

GET  /api/v1/repositories         – list connected repositories
GET  /api/v1/repositories/{id}    – get repository details
PUT  /api/v1/repositories/{id}    – update repair policy
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.github import Repository
from app.db.session import get_db

router = APIRouter(tags=["repositories"])


class RepositorySummary(BaseModel):
    id: uuid.UUID
    full_name: str
    default_branch: str
    language: str | None
    is_active: bool
    repair_policy: dict | None

    model_config = {"from_attributes": True}


class RepairPolicyUpdate(BaseModel):
    max_repair_attempts: int | None = None
    allowed_languages: list[str] | None = None
    auto_repair_enabled: bool | None = None


@router.get(
    "/repositories",
    response_model=list[RepositorySummary],
    summary="List connected repositories",
)
async def list_repositories(
    db: AsyncSession = Depends(get_db),
) -> list[RepositorySummary]:
    result = await db.execute(
        select(Repository).where(Repository.is_active.is_(True)).order_by(Repository.full_name)
    )
    repos = result.scalars().all()
    return [RepositorySummary.model_validate(r) for r in repos]


@router.get(
    "/repositories/{repository_id}",
    response_model=RepositorySummary,
    summary="Get repository details",
)
async def get_repository(
    repository_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> RepositorySummary:
    result = await db.execute(
        select(Repository).where(Repository.id == repository_id)
    )
    repo = result.scalar_one_or_none()
    if not repo:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Repository not found")
    return RepositorySummary.model_validate(repo)


@router.put(
    "/repositories/{repository_id}/policy",
    response_model=RepositorySummary,
    summary="Update repair policy for a repository",
)
async def update_repair_policy(
    repository_id: uuid.UUID,
    policy: RepairPolicyUpdate,
    db: AsyncSession = Depends(get_db),
) -> RepositorySummary:
    result = await db.execute(
        select(Repository).where(Repository.id == repository_id)
    )
    repo = result.scalar_one_or_none()
    if not repo:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Repository not found")

    current_policy = repo.repair_policy or {}
    updates = policy.model_dump(exclude_none=True)
    current_policy.update(updates)
    repo.repair_policy = current_policy

    await db.flush()
    return RepositorySummary.model_validate(repo)
