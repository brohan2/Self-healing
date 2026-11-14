"""
GitHub integration ORM models.

Tables:
- users
- github_installations
- repositories
- webhook_events
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Platform users (dashboard access only)."""

    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # relationships
    installations: Mapped[list[GitHubInstallation]] = relationship(
        back_populates="created_by_user"
    )


class GitHubInstallation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A GitHub App installation on an org or user account."""

    __tablename__ = "github_installations"

    installation_id: Mapped[int] = mapped_column(Integer, unique=True, nullable=False, index=True)
    account_login: Mapped[str] = mapped_column(String(200), nullable=False)
    account_type: Mapped[str] = mapped_column(String(50), nullable=False)  # User | Organization
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    # relationships
    created_by_user: Mapped[User | None] = relationship(back_populates="installations")
    repositories: Mapped[list[Repository]] = relationship(back_populates="installation")


class Repository(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A GitHub repository connected to AutoFix AI."""

    __tablename__ = "repositories"
    __table_args__ = (
        UniqueConstraint("installation_id", "github_repo_id", name="uq_repo_installation"),
    )

    installation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("github_installations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    github_repo_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    full_name: Mapped[str] = mapped_column(String(500), nullable=False)  # org/repo
    default_branch: Mapped[str] = mapped_column(String(200), nullable=False, default="main")
    language: Mapped[str | None] = mapped_column(String(100), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Repair policy stored as JSONB (flexible schema)
    repair_policy: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # relationships
    installation: Mapped[GitHubInstallation] = relationship(back_populates="repositories")
    webhook_events: Mapped[list[WebhookEvent]] = relationship(back_populates="repository")


class WebhookEvent(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """
    Raw GitHub webhook delivery record.

    The github_delivery_id is the idempotency key — duplicate deliveries
    are detected by querying this column before processing.
    """

    __tablename__ = "webhook_events"

    github_delivery_id: Mapped[str] = mapped_column(
        String(100), unique=True, nullable=False, index=True
    )
    event_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    action: Mapped[str | None] = mapped_column(String(100), nullable=True)

    repository_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("repositories.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Raw payload stored as JSONB for auditability / replay
    raw_payload: Mapped[dict] = mapped_column(JSON, nullable=False)

    # Processing state
    processed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    processed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    processing_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    # relationships
    repository: Mapped[Repository | None] = relationship(back_populates="webhook_events")
