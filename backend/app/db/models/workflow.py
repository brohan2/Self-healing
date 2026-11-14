"""
Workflow run and job ORM models.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class WorkflowRun(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A single GitHub Actions workflow_run execution."""

    __tablename__ = "workflow_runs"

    repository_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("repositories.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    webhook_event_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("webhook_events.id", ondelete="SET NULL"),
        nullable=True,
    )

    # GitHub-provided identifiers
    github_run_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    github_run_number: Mapped[int] = mapped_column(Integer, nullable=False)
    workflow_name: Mapped[str] = mapped_column(String(500), nullable=False)
    workflow_path: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Commit context
    head_sha: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    head_branch: Mapped[str | None] = mapped_column(String(500), nullable=True)
    head_commit_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Run outcome
    status: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    conclusion: Mapped[str | None] = mapped_column(String(50), nullable=True)

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # relationships
    jobs: Mapped[list["WorkflowJob"]] = relationship(back_populates="workflow_run")
    investigations: Mapped[list["Investigation"]] = relationship(
        "Investigation", back_populates="workflow_run"
    )


class WorkflowJob(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """An individual job within a workflow run."""

    __tablename__ = "workflow_jobs"

    workflow_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workflow_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    github_job_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False)
    conclusion: Mapped[str | None] = mapped_column(String(50), nullable=True)

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Compressed log text (up to 10 MB in GitHub)
    log_text: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Structured step information
    steps: Mapped[list | None] = mapped_column(JSON, nullable=True)

    # relationships
    workflow_run: Mapped["WorkflowRun"] = relationship(back_populates="jobs")
