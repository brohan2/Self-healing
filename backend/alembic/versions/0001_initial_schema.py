"""Initial schema – all Phase 1 tables.

Revision ID: 0001
Revises:
Create Date: 2024-01-01 00:00:00.000000
"""
from __future__ import annotations

import uuid
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ------------------------------------------------------------------ #
    # users
    # ------------------------------------------------------------------ #
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column("email", sa.String(320), nullable=False, unique=True),
        sa.Column("display_name", sa.String(200), nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
    )
    op.create_index("ix_users_email", "users", ["email"])
    op.create_index("ix_users_id", "users", ["id"])

    # ------------------------------------------------------------------ #
    # github_installations
    # ------------------------------------------------------------------ #
    op.create_table(
        "github_installations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column("installation_id", sa.Integer, nullable=False, unique=True),
        sa.Column("account_login", sa.String(200), nullable=False),
        sa.Column("account_type", sa.String(50), nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_github_installations_id", "github_installations", ["id"])
    op.create_index("ix_github_installations_installation_id", "github_installations", ["installation_id"])

    # ------------------------------------------------------------------ #
    # repositories
    # ------------------------------------------------------------------ #
    op.create_table(
        "repositories",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column("installation_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("github_installations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("github_repo_id", sa.Integer, nullable=False),
        sa.Column("full_name", sa.String(500), nullable=False),
        sa.Column("default_branch", sa.String(200), nullable=False, server_default="main"),
        sa.Column("language", sa.String(100), nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("repair_policy", postgresql.JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_repositories_id", "repositories", ["id"])
    op.create_index("ix_repositories_installation_id", "repositories", ["installation_id"])
    op.create_index("ix_repositories_github_repo_id", "repositories", ["github_repo_id"])
    op.create_unique_constraint("uq_repo_installation", "repositories", ["installation_id", "github_repo_id"])

    # ------------------------------------------------------------------ #
    # webhook_events
    # ------------------------------------------------------------------ #
    op.create_table(
        "webhook_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column("github_delivery_id", sa.String(100), nullable=False, unique=True),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("action", sa.String(100), nullable=True),
        sa.Column("repository_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("repositories.id", ondelete="SET NULL"), nullable=True),
        sa.Column("raw_payload", postgresql.JSONB, nullable=False),
        sa.Column("processed", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("processing_error", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_webhook_events_id", "webhook_events", ["id"])
    op.create_index("ix_webhook_events_github_delivery_id", "webhook_events", ["github_delivery_id"])
    op.create_index("ix_webhook_events_event_type", "webhook_events", ["event_type"])
    op.create_index("ix_webhook_events_repository_id", "webhook_events", ["repository_id"])

    # ------------------------------------------------------------------ #
    # workflow_runs
    # ------------------------------------------------------------------ #
    op.create_table(
        "workflow_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column("repository_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False),
        sa.Column("webhook_event_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("webhook_events.id", ondelete="SET NULL"), nullable=True),
        sa.Column("github_run_id", sa.BigInteger, nullable=False),
        sa.Column("github_run_number", sa.Integer, nullable=False),
        sa.Column("workflow_name", sa.String(500), nullable=False),
        sa.Column("workflow_path", sa.String(500), nullable=True),
        sa.Column("head_sha", sa.String(40), nullable=False),
        sa.Column("head_branch", sa.String(500), nullable=True),
        sa.Column("head_commit_message", sa.Text, nullable=True),
        sa.Column("status", sa.String(50), nullable=False),
        sa.Column("conclusion", sa.String(50), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_workflow_runs_id", "workflow_runs", ["id"])
    op.create_index("ix_workflow_runs_repository_id", "workflow_runs", ["repository_id"])
    op.create_index("ix_workflow_runs_github_run_id", "workflow_runs", ["github_run_id"])
    op.create_index("ix_workflow_runs_head_sha", "workflow_runs", ["head_sha"])
    op.create_index("ix_workflow_runs_status", "workflow_runs", ["status"])

    # ------------------------------------------------------------------ #
    # workflow_jobs
    # ------------------------------------------------------------------ #
    op.create_table(
        "workflow_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column("workflow_run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("workflow_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("github_job_id", sa.BigInteger, nullable=False),
        sa.Column("name", sa.String(500), nullable=False),
        sa.Column("status", sa.String(50), nullable=False),
        sa.Column("conclusion", sa.String(50), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("log_text", sa.Text, nullable=True),
        sa.Column("steps", postgresql.JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_workflow_jobs_id", "workflow_jobs", ["id"])
    op.create_index("ix_workflow_jobs_workflow_run_id", "workflow_jobs", ["workflow_run_id"])
    op.create_index("ix_workflow_jobs_github_job_id", "workflow_jobs", ["github_job_id"])

    # ------------------------------------------------------------------ #
    # incidents
    # ------------------------------------------------------------------ #
    op.create_table(
        "incidents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column("repository_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("status", sa.String(50), nullable=False, server_default="open"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_incidents_id", "incidents", ["id"])
    op.create_index("ix_incidents_repository_id", "incidents", ["repository_id"])

    # ------------------------------------------------------------------ #
    # investigations
    # ------------------------------------------------------------------ #
    op.create_table(
        "investigations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column("workflow_run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("workflow_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("incident_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("incidents.id", ondelete="SET NULL"), nullable=True),
        sa.Column("status", sa.String(50), nullable=False, server_default="PENDING"),
        sa.Column("failure_category", sa.String(100), nullable=True),
        sa.Column("error_summary", sa.Text, nullable=True),
        sa.Column("result", postgresql.JSONB, nullable=True),
        sa.Column("confidence", sa.Float, nullable=True),
        sa.Column("suspected_files", postgresql.JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_investigations_id", "investigations", ["id"])
    op.create_index("ix_investigations_workflow_run_id", "investigations", ["workflow_run_id"])
    op.create_index("ix_investigations_incident_id", "investigations", ["incident_id"])
    op.create_index("ix_investigations_status", "investigations", ["status"])

    # ------------------------------------------------------------------ #
    # repair_attempts
    # ------------------------------------------------------------------ #
    op.create_table(
        "repair_attempts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column("investigation_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("investigations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(50), nullable=False, server_default="RECEIVED"),
        sa.Column("attempt_number", sa.Integer, nullable=False, server_default="1"),
        sa.Column("max_attempts", sa.Integer, nullable=False, server_default="3"),
        sa.Column("worker_id", sa.String(200), nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_repair_attempts_id", "repair_attempts", ["id"])
    op.create_index("ix_repair_attempts_investigation_id", "repair_attempts", ["investigation_id"])
    op.create_index("ix_repair_attempts_status", "repair_attempts", ["status"])

    # ------------------------------------------------------------------ #
    # agent_executions
    # ------------------------------------------------------------------ #
    op.create_table(
        "agent_executions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column("repair_attempt_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("repair_attempts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("investigation_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("investigations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("provider", sa.String(100), nullable=False),
        sa.Column("model", sa.String(200), nullable=False),
        sa.Column("prompt_tokens", sa.Integer, nullable=False, server_default="0"),
        sa.Column("completion_tokens", sa.Integer, nullable=False, server_default="0"),
        sa.Column("total_tokens", sa.Integer, nullable=False, server_default="0"),
        sa.Column("iterations", sa.Integer, nullable=False, server_default="0"),
        sa.Column("duration_seconds", sa.Float, nullable=True),
        sa.Column("tool_calls", postgresql.JSONB, nullable=True),
        sa.Column("result_summary", sa.Text, nullable=True),
        sa.Column("succeeded", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_agent_executions_id", "agent_executions", ["id"])
    op.create_index("ix_agent_executions_repair_attempt_id", "agent_executions", ["repair_attempt_id"])
    op.create_index("ix_agent_executions_investigation_id", "agent_executions", ["investigation_id"])

    # ------------------------------------------------------------------ #
    # generated_patches
    # ------------------------------------------------------------------ #
    op.create_table(
        "generated_patches",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column("repair_attempt_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("repair_attempts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("diff_text", sa.Text, nullable=False),
        sa.Column("affected_files", postgresql.JSONB, nullable=True),
        sa.Column("patch_size_bytes", sa.Integer, nullable=False, server_default="0"),
        sa.Column("is_valid", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("validation_error", sa.Text, nullable=True),
        sa.Column("root_cause_explanation", sa.Text, nullable=True),
        sa.Column("confidence", sa.Float, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_generated_patches_id", "generated_patches", ["id"])
    op.create_index("ix_generated_patches_repair_attempt_id", "generated_patches", ["repair_attempt_id"])

    # ------------------------------------------------------------------ #
    # validation_runs
    # ------------------------------------------------------------------ #
    op.create_table(
        "validation_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column("repair_attempt_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("repair_attempts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("patch_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("generated_patches.id", ondelete="SET NULL"), nullable=True),
        sa.Column("all_checks_passed", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("duration_seconds", sa.Float, nullable=True),
        sa.Column("timed_out", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("install_result", postgresql.JSONB, nullable=True),
        sa.Column("test_result", postgresql.JSONB, nullable=True),
        sa.Column("regression_test_result", postgresql.JSONB, nullable=True),
        sa.Column("lint_result", postgresql.JSONB, nullable=True),
        sa.Column("build_result", postgresql.JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_validation_runs_id", "validation_runs", ["id"])
    op.create_index("ix_validation_runs_repair_attempt_id", "validation_runs", ["repair_attempt_id"])

    # ------------------------------------------------------------------ #
    # pull_requests
    # ------------------------------------------------------------------ #
    op.create_table(
        "pull_requests",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column("repair_attempt_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("repair_attempts.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("github_pr_number", sa.Integer, nullable=False),
        sa.Column("github_pr_url", sa.String(500), nullable=False),
        sa.Column("branch_name", sa.String(500), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("body", sa.Text, nullable=True),
        sa.Column("is_merged", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("is_closed", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_pull_requests_id", "pull_requests", ["id"])
    op.create_index("ix_pull_requests_repair_attempt_id", "pull_requests", ["repair_attempt_id"])

    # ------------------------------------------------------------------ #
    # audit_logs
    # ------------------------------------------------------------------ #
    op.create_table(
        "audit_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column("repair_attempt_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("repair_attempts.id", ondelete="SET NULL"), nullable=True),
        sa.Column("investigation_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("investigations.id", ondelete="SET NULL"), nullable=True),
        sa.Column("repository_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("repositories.id", ondelete="SET NULL"), nullable=True),
        sa.Column("actor", sa.String(200), nullable=False),
        sa.Column("action", sa.String(200), nullable=False),
        sa.Column("summary", sa.Text, nullable=True),
        sa.Column("details", postgresql.JSONB, nullable=True),
        sa.Column("correlation_id", sa.String(100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_audit_logs_id", "audit_logs", ["id"])
    op.create_index("ix_audit_logs_repair_attempt_id", "audit_logs", ["repair_attempt_id"])
    op.create_index("ix_audit_logs_investigation_id", "audit_logs", ["investigation_id"])
    op.create_index("ix_audit_logs_repository_id", "audit_logs", ["repository_id"])
    op.create_index("ix_audit_logs_action", "audit_logs", ["action"])
    op.create_index("ix_audit_logs_correlation_id", "audit_logs", ["correlation_id"])


def downgrade() -> None:
    op.drop_table("audit_logs")
    op.drop_table("pull_requests")
    op.drop_table("validation_runs")
    op.drop_table("generated_patches")
    op.drop_table("agent_executions")
    op.drop_table("repair_attempts")
    op.drop_table("investigations")
    op.drop_table("incidents")
    op.drop_table("workflow_jobs")
    op.drop_table("workflow_runs")
    op.drop_table("webhook_events")
    op.drop_table("repositories")
    op.drop_table("github_installations")
    op.drop_table("users")
