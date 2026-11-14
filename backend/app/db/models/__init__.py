"""
ORM model registry.

Import Base and all model classes from here so Alembic can discover them.
"""
from app.db.models.base import Base
from app.db.models.github import GitHubInstallation, Repository, User, WebhookEvent
from app.db.models.workflow import WorkflowJob, WorkflowRun
from app.db.models.investigation import FailureCategory, Incident, Investigation
from app.db.models.repair import (
    AgentExecution,
    GeneratedPatch,
    RepairAttempt,
    RepairStatus,
    ValidationRun,
    VALID_TRANSITIONS,
)
from app.db.models.pull_request import PullRequest
from app.db.models.audit import AuditLog

__all__ = [
    "Base",
    # github
    "User",
    "GitHubInstallation",
    "Repository",
    "WebhookEvent",
    # workflow
    "WorkflowRun",
    "WorkflowJob",
    # investigation
    "FailureCategory",
    "Incident",
    "Investigation",
    # repair
    "RepairAttempt",
    "RepairStatus",
    "VALID_TRANSITIONS",
    "AgentExecution",
    "GeneratedPatch",
    "ValidationRun",
    # pr
    "PullRequest",
    # audit
    "AuditLog",
]
