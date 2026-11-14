"""
Pull request ORM model.
"""
from __future__ import annotations

import uuid

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class PullRequest(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A GitHub Pull Request created by AutoFix AI."""

    __tablename__ = "pull_requests"

    repair_attempt_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("repair_attempts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        unique=True,
    )

    github_pr_number: Mapped[int] = mapped_column(Integer, nullable=False)
    github_pr_url: Mapped[str] = mapped_column(String(500), nullable=False)
    branch_name: Mapped[str] = mapped_column(String(500), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_merged: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_closed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # relationships
    repair_attempt: Mapped["RepairAttempt"] = relationship("RepairAttempt", back_populates="pull_request")
