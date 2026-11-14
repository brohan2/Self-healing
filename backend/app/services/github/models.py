"""
Pydantic models for GitHub API responses.

These are only the fields we actually use — not complete GitHub schemas.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class GitHubRepository(BaseModel):
    id: int
    full_name: str
    default_branch: str = "main"
    language: str | None = None
    private: bool = False


class GitHubCommit(BaseModel):
    id: str  # SHA
    message: str = ""
    timestamp: str = ""


class GitHubWorkflowRun(BaseModel):
    id: int
    run_number: int
    name: str
    path: str | None = None
    head_sha: str
    head_branch: str | None = None
    head_commit: GitHubCommit | None = None
    status: str
    conclusion: str | None = None
    workflow_id: int | None = None
    repository: GitHubRepository | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    run_started_at: datetime | None = None
    html_url: str = ""


class GitHubWorkflowJobStep(BaseModel):
    name: str
    status: str
    conclusion: str | None = None
    number: int
    started_at: datetime | None = None
    completed_at: datetime | None = None


class GitHubWorkflowJob(BaseModel):
    id: int
    name: str
    status: str
    conclusion: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    steps: list[GitHubWorkflowJobStep] = Field(default_factory=list)
    html_url: str = ""


class GitHubInstallationPayload(BaseModel):
    """Payload of a GitHub App installation event."""
    id: int
    account: dict[str, Any]
    app_id: int


class GitHubWorkflowRunEvent(BaseModel):
    """Top-level workflow_run webhook payload."""
    action: str
    workflow_run: GitHubWorkflowRun
    repository: GitHubRepository
    installation: GitHubInstallationPayload | None = None
