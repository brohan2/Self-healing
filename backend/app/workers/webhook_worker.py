"""
Webhook Worker.

Consumes from: autofix:webhooks
Produces to:   autofix:investigations

For each `workflow_run` event with conclusion=failure|cancelled:
1. Parse the webhook payload
2. Resolve or create GitHubInstallation + Repository records
3. Create WorkflowRun record
4. Create RepairAttempt record (status=RECEIVED)
5. Write audit log entry
6. Enqueue to autofix:investigations stream
7. Mark WebhookEvent as processed

Idempotent: if a WorkflowRun for this github_run_id already exists,
skip creation and do not re-enqueue.
"""
from __future__ import annotations

import json
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.audit import AuditLog
from app.db.models.github import GitHubInstallation, Repository, WebhookEvent
from app.db.models.repair import RepairAttempt, RepairStatus
from app.db.models.workflow import WorkflowRun
from app.db.session import get_db_session
from app.observability.logging import get_logger
from app.observability.metrics import REPAIRS_ATTEMPTED
from app.workers.base import BaseWorker

logger = get_logger(__name__)

# Only process these conclusions
_ACTIONABLE_CONCLUSIONS = {"failure", "cancelled", "timed_out"}


class WebhookWorker(BaseWorker):
    """
    Processes raw webhook events from the autofix:webhooks stream.
    """

    def __init__(self) -> None:
        from app.config import get_settings
        settings = get_settings()
        super().__init__(stream_key=settings.redis_stream_webhooks)
        self._settings = settings

    async def process_message(
        self,
        message_id: str,
        fields: dict[str, str],
    ) -> None:
        event_id = fields.get("event_id")
        if not event_id:
            logger.warning("webhook_worker_missing_event_id", message_id=message_id)
            return

        async with get_db_session() as db:
            await self._process_event(db, uuid.UUID(event_id), message_id)

    async def _process_event(
        self,
        db: AsyncSession,
        event_id: uuid.UUID,
        message_id: str,
    ) -> None:
        # ------------------------------------------------------------------ #
        # 1. Load the WebhookEvent
        # ------------------------------------------------------------------ #
        result = await db.execute(
            select(WebhookEvent).where(WebhookEvent.id == event_id)
        )
        event = result.scalar_one_or_none()
        if not event:
            logger.warning(
                "webhook_worker_event_not_found",
                event_id=str(event_id),
            )
            return

        if event.processed:
            logger.info(
                "webhook_worker_already_processed",
                event_id=str(event_id),
                delivery_id=event.github_delivery_id,
            )
            return

        payload = event.raw_payload

        # ------------------------------------------------------------------ #
        # 2. Only handle workflow_run completed events
        # ------------------------------------------------------------------ #
        if event.event_type != "workflow_run" or event.action != "completed":
            logger.debug(
                "webhook_worker_skipping_non_failure_event",
                event_type=event.event_type,
                action=event.action,
            )
            event.processed = True
            await db.flush()
            return

        workflow_run_data = payload.get("workflow_run", {})
        conclusion = workflow_run_data.get("conclusion")

        if conclusion not in _ACTIONABLE_CONCLUSIONS:
            logger.debug(
                "webhook_worker_skipping_non_failure_conclusion",
                conclusion=conclusion,
            )
            event.processed = True
            await db.flush()
            return

        # ------------------------------------------------------------------ #
        # 3. Resolve Installation
        # ------------------------------------------------------------------ #
        installation_data = payload.get("installation", {})
        github_installation_id = installation_data.get("id")
        if not github_installation_id:
            logger.warning(
                "webhook_worker_no_installation_id",
                event_id=str(event_id),
            )
            event.processed = True
            await db.flush()
            return

        inst_result = await db.execute(
            select(GitHubInstallation).where(
                GitHubInstallation.installation_id == github_installation_id
            )
        )
        installation = inst_result.scalar_one_or_none()
        if not installation:
            repo_data = payload.get("repository", {})
            account_login = installation_data.get("account", {}).get("login", "unknown")
            account_type = installation_data.get("account", {}).get("type", "Organization")
            installation = GitHubInstallation(
                installation_id=github_installation_id,
                account_login=account_login,
                account_type=account_type,
                is_active=True,
            )
            db.add(installation)
            await db.flush()
            logger.info(
                "webhook_worker_created_installation",
                installation_id=github_installation_id,
                account=account_login,
            )

        # ------------------------------------------------------------------ #
        # 4. Resolve Repository
        # ------------------------------------------------------------------ #
        repo_data = payload.get("repository", {})
        github_repo_id = repo_data.get("id")
        full_name = repo_data.get("full_name", "")

        repo_result = await db.execute(
            select(Repository).where(
                Repository.github_repo_id == github_repo_id,
                Repository.installation_id == installation.id,
            )
        )
        repository = repo_result.scalar_one_or_none()
        if not repository:
            repository = Repository(
                installation_id=installation.id,
                github_repo_id=github_repo_id,
                full_name=full_name,
                default_branch=repo_data.get("default_branch", "main"),
                language=repo_data.get("language"),
                is_active=True,
            )
            db.add(repository)
            await db.flush()
            logger.info(
                "webhook_worker_created_repository",
                repo=full_name,
            )

        # ------------------------------------------------------------------ #
        # 5. Idempotency check for WorkflowRun
        # ------------------------------------------------------------------ #
        github_run_id = workflow_run_data.get("id")
        existing_run = await db.execute(
            select(WorkflowRun).where(
                WorkflowRun.github_run_id == github_run_id,
                WorkflowRun.repository_id == repository.id,
            )
        )
        if existing_run.scalar_one_or_none():
            logger.info(
                "webhook_worker_run_already_exists",
                github_run_id=github_run_id,
            )
            event.processed = True
            await db.flush()
            return

        # ------------------------------------------------------------------ #
        # 6. Create WorkflowRun
        # ------------------------------------------------------------------ #
        head_commit = workflow_run_data.get("head_commit") or {}
        workflow_run = WorkflowRun(
            repository_id=repository.id,
            webhook_event_id=event.id,
            github_run_id=github_run_id,
            github_run_number=workflow_run_data.get("run_number", 0),
            workflow_name=workflow_run_data.get("name", ""),
            workflow_path=workflow_run_data.get("path"),
            head_sha=workflow_run_data.get("head_sha", ""),
            head_branch=workflow_run_data.get("head_branch"),
            head_commit_message=head_commit.get("message", ""),
            status=workflow_run_data.get("status", "completed"),
            conclusion=conclusion,
        )
        db.add(workflow_run)
        await db.flush()

        # ------------------------------------------------------------------ #
        # 7. Create RepairAttempt
        # ------------------------------------------------------------------ #
        # We need an investigation first — create a stub investigation
        from app.db.models.investigation import Investigation, InvestigationStatus
        investigation = Investigation(
            workflow_run_id=workflow_run.id,
            status=InvestigationStatus.PENDING,
        )
        db.add(investigation)
        await db.flush()

        max_attempts = self._settings.max_repair_attempts
        # Check repository repair policy
        if repository.repair_policy:
            max_attempts = repository.repair_policy.get(
                "max_repair_attempts", max_attempts
            )

        repair_attempt = RepairAttempt(
            investigation_id=investigation.id,
            status=RepairStatus.RECEIVED,
            attempt_number=1,
            max_attempts=max_attempts,
        )
        db.add(repair_attempt)
        await db.flush()

        REPAIRS_ATTEMPTED.labels(repository=full_name).inc()

        # ------------------------------------------------------------------ #
        # 8. Audit log
        # ------------------------------------------------------------------ #
        audit = AuditLog(
            repair_attempt_id=repair_attempt.id,
            investigation_id=investigation.id,
            repository_id=repository.id,
            actor="webhook_worker",
            action="repair_attempt_created",
            summary=f"Repair attempt created for {full_name} run #{workflow_run_data.get('run_number')}",
            details={
                "github_run_id": github_run_id,
                "conclusion": conclusion,
                "head_sha": workflow_run.head_sha,
                "head_branch": workflow_run.head_branch,
            },
        )
        db.add(audit)

        # ------------------------------------------------------------------ #
        # 9. Mark webhook processed
        # ------------------------------------------------------------------ #
        event.processed = True
        from datetime import datetime, timezone
        event.processed_at = datetime.now(timezone.utc)
        await db.flush()

        # ------------------------------------------------------------------ #
        # 10. Enqueue to investigation stream
        # ------------------------------------------------------------------ #
        await self.publish(
            self._settings.redis_stream_investigations,
            {
                "repair_attempt_id": str(repair_attempt.id),
                "investigation_id": str(investigation.id),
                "workflow_run_id": str(workflow_run.id),
                "installation_id": str(github_installation_id),
            },
        )

        logger.info(
            "webhook_worker_enqueued_investigation",
            repair_attempt_id=str(repair_attempt.id),
            repo=full_name,
            github_run_id=github_run_id,
            conclusion=conclusion,
        )
