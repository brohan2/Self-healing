"""
Repair lifecycle ORM models.

Tables:
- repair_attempts     – lifecycle state machine per repair job
- agent_executions    – each AI agent invocation
- generated_patches   – validated unified diffs
- validation_runs     – sandbox execution results
"""
from __future__ import annotations

import uuid
from enum import StrEnum

from sqlalchemy import Boolean, Float, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class RepairStatus(StrEnum):
    RECEIVED = "RECEIVED"
    VALIDATING = "VALIDATING"
    FETCHING_LOGS = "FETCHING_LOGS"
    INVESTIGATING = "INVESTIGATING"
    ANALYZING_REPOSITORY = "ANALYZING_REPOSITORY"
    GENERATING_PATCH = "GENERATING_PATCH"
    VALIDATING_PATCH = "VALIDATING_PATCH"
    BUILDING = "BUILDING"
    TESTING = "TESTING"
    REPAIR_RETRY = "REPAIR_RETRY"
    CREATING_BRANCH = "CREATING_BRANCH"
    PUSHING_CHANGES = "PUSHING_CHANGES"
    CREATING_PULL_REQUEST = "CREATING_PULL_REQUEST"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    ESCALATED = "ESCALATED"


# Defines which transitions are permitted.
# Keys are current state; values are the set of reachable next states.
VALID_TRANSITIONS: dict[RepairStatus, set[RepairStatus]] = {
    RepairStatus.RECEIVED: {RepairStatus.VALIDATING, RepairStatus.FAILED},
    RepairStatus.VALIDATING: {RepairStatus.FETCHING_LOGS, RepairStatus.FAILED},
    RepairStatus.FETCHING_LOGS: {RepairStatus.INVESTIGATING, RepairStatus.FAILED},
    RepairStatus.INVESTIGATING: {RepairStatus.ANALYZING_REPOSITORY, RepairStatus.ESCALATED, RepairStatus.FAILED},
    RepairStatus.ANALYZING_REPOSITORY: {RepairStatus.GENERATING_PATCH, RepairStatus.ESCALATED, RepairStatus.FAILED},
    RepairStatus.GENERATING_PATCH: {RepairStatus.VALIDATING_PATCH, RepairStatus.REPAIR_RETRY, RepairStatus.FAILED},
    RepairStatus.VALIDATING_PATCH: {RepairStatus.BUILDING, RepairStatus.REPAIR_RETRY, RepairStatus.FAILED},
    RepairStatus.BUILDING: {RepairStatus.TESTING, RepairStatus.REPAIR_RETRY, RepairStatus.FAILED},
    RepairStatus.TESTING: {RepairStatus.CREATING_BRANCH, RepairStatus.REPAIR_RETRY, RepairStatus.FAILED},
    RepairStatus.REPAIR_RETRY: {RepairStatus.GENERATING_PATCH, RepairStatus.ESCALATED, RepairStatus.FAILED},
    RepairStatus.CREATING_BRANCH: {RepairStatus.PUSHING_CHANGES, RepairStatus.FAILED},
    RepairStatus.PUSHING_CHANGES: {RepairStatus.CREATING_PULL_REQUEST, RepairStatus.FAILED},
    RepairStatus.CREATING_PULL_REQUEST: {RepairStatus.COMPLETED, RepairStatus.FAILED},
    RepairStatus.COMPLETED: set(),  # terminal
    RepairStatus.FAILED: set(),     # terminal
    RepairStatus.ESCALATED: set(),  # terminal
}


class RepairAttempt(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """
    Central state machine record for a single repair lifecycle.

    One RepairAttempt is created per workflow failure.
    It progresses through RepairStatus states.
    """

    __tablename__ = "repair_attempts"

    investigation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("investigations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default=RepairStatus.RECEIVED,
        index=True,
    )

    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=3)

    # Assigned worker instance (for crash detection)
    worker_id: Mapped[str | None] = mapped_column(String(200), nullable=True)

    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # relationships
    investigation: Mapped["Investigation"] = relationship("Investigation", back_populates="repair_attempts")
    agent_executions: Mapped[list["AgentExecution"]] = relationship(
        "AgentExecution", back_populates="repair_attempt"
    )
    generated_patches: Mapped[list["GeneratedPatch"]] = relationship(
        "GeneratedPatch", back_populates="repair_attempt"
    )
    validation_runs: Mapped[list["ValidationRun"]] = relationship(
        "ValidationRun", back_populates="repair_attempt"
    )
    pull_request: Mapped["PullRequest | None"] = relationship(
        "PullRequest", back_populates="repair_attempt"
    )


class AgentExecution(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Records a single AI agent invocation including token usage."""

    __tablename__ = "agent_executions"

    repair_attempt_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("repair_attempts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    investigation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("investigations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    provider: Mapped[str] = mapped_column(String(100), nullable=False)
    model: Mapped[str] = mapped_column(String(200), nullable=False)
    prompt_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    iterations: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)

    # tool_calls is a JSONB list of {tool, args, result} objects
    tool_calls: Mapped[list | None] = mapped_column(JSON, nullable=True)
    result_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    succeeded: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # relationships
    repair_attempt: Mapped["RepairAttempt"] = relationship(back_populates="agent_executions")
    investigation: Mapped["Investigation"] = relationship("Investigation", back_populates="agent_executions")


class GeneratedPatch(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A unified diff patch produced by the AI agent."""

    __tablename__ = "generated_patches"

    repair_attempt_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("repair_attempts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    diff_text: Mapped[str] = mapped_column(Text, nullable=False)
    affected_files: Mapped[list | None] = mapped_column(JSON, nullable=True)
    patch_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_valid: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    validation_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    root_cause_explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)

    # relationships (GeneratedPatch)
    repair_attempt: Mapped["RepairAttempt"] = relationship(back_populates="generated_patches")


class ValidationRun(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Result of a sandbox execution for a generated patch."""

    __tablename__ = "validation_runs"

    repair_attempt_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("repair_attempts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    patch_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("generated_patches.id", ondelete="SET NULL"),
        nullable=True,
    )

    all_checks_passed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    timed_out: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Per-step results stored as JSONB
    install_result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    test_result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    regression_test_result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    lint_result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    build_result: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # relationships (ValidationRun)
    repair_attempt: Mapped["RepairAttempt"] = relationship(back_populates="validation_runs")
