"""
Investigation and incident ORM models.
"""
from __future__ import annotations

import uuid
from enum import StrEnum

from sqlalchemy import Float, ForeignKey, JSON, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class FailureCategory(StrEnum):
    COMPILATION_ERROR = "COMPILATION_ERROR"
    SYNTAX_ERROR = "SYNTAX_ERROR"
    UNIT_TEST_FAILURE = "UNIT_TEST_FAILURE"
    INTEGRATION_TEST_FAILURE = "INTEGRATION_TEST_FAILURE"
    DEPENDENCY_ERROR = "DEPENDENCY_ERROR"
    TYPE_ERROR = "TYPE_ERROR"
    LINT_FAILURE = "LINT_FAILURE"
    CONFIGURATION_ERROR = "CONFIGURATION_ERROR"
    ENVIRONMENT_FAILURE = "ENVIRONMENT_FAILURE"
    UNKNOWN = "UNKNOWN"


class InvestigationStatus(StrEnum):
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class Incident(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Top-level grouping for related workflow failures."""

    __tablename__ = "incidents"

    repository_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("repositories.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="open")

    investigations: Mapped[list[Investigation]] = relationship(back_populates="incident")


class Investigation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """
    Investigation result for a single workflow_run failure.

    Produced by the InvestigationEngine after parsing logs and
    classifying the failure.
    """

    __tablename__ = "investigations"

    workflow_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workflow_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    incident_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("incidents.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default=InvestigationStatus.PENDING,
        index=True,
    )
    failure_category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_summary: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Structured results stored as JSONB (flexible schema between categories)
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    suspected_files: Mapped[list | None] = mapped_column(JSON, nullable=True)

    # relationships
    workflow_run: Mapped["WorkflowRun"] = relationship("WorkflowRun", back_populates="investigations")
    incident: Mapped[Incident | None] = relationship(back_populates="investigations")
    repair_attempts: Mapped[list["RepairAttempt"]] = relationship(
        "RepairAttempt", back_populates="investigation"
    )
    agent_executions: Mapped[list["AgentExecution"]] = relationship(
        "AgentExecution", back_populates="investigation"
    )
