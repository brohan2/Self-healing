"""
Investigation Engine.

Orchestrates log retrieval + parsing + classification for a single
workflow run. Produces an InvestigationResult and persists it.
"""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.investigation import Investigation, InvestigationStatus
from app.db.models.workflow import WorkflowJob, WorkflowRun
from app.observability.logging import get_logger
from app.services.github.client import GitHubClient
from app.services.investigation.classifier import InvestigationResult, classify_failure
from app.services.investigation.log_parser import parse_log

logger = get_logger(__name__)


class InvestigationEngine:
    """
    Runs the full investigation pipeline for a workflow failure.

    Steps:
    1. Load WorkflowRun + repository from DB
    2. Fetch failed jobs from GitHub
    3. Download logs for failed jobs
    4. Parse logs
    5. Classify failure
    6. Persist Investigation record
    7. Return InvestigationResult
    """

    def __init__(
        self,
        db: AsyncSession,
        github_client: GitHubClient | None = None,
    ) -> None:
        self._db = db
        self._github = github_client or GitHubClient()

    async def investigate(
        self,
        workflow_run_id: uuid.UUID,
        installation_id: int,
    ) -> Investigation:
        """
        Run the full investigation for a workflow run.

        :param workflow_run_id: internal UUID of the WorkflowRun record
        :param installation_id: GitHub App installation ID
        :returns: persisted Investigation ORM object
        """
        # ------------------------------------------------------------------ #
        # 1. Load workflow run
        # ------------------------------------------------------------------ #
        result = await self._db.execute(
            select(WorkflowRun).where(WorkflowRun.id == workflow_run_id)
        )
        workflow_run = result.scalar_one_or_none()
        if not workflow_run:
            raise ValueError(f"WorkflowRun {workflow_run_id} not found")

        # Load repository to get owner/repo
        from app.db.models.github import Repository
        repo_result = await self._db.execute(
            select(Repository).where(Repository.id == workflow_run.repository_id)
        )
        repository = repo_result.scalar_one_or_none()
        if not repository:
            raise ValueError(f"Repository for run {workflow_run_id} not found")

        owner, repo_name = repository.full_name.split("/", 1)

        logger.info(
            "investigation_starting",
            workflow_run_id=str(workflow_run_id),
            repo=repository.full_name,
            run_id=workflow_run.github_run_id,
        )

        # Create Investigation record in PENDING state
        investigation = Investigation(
            workflow_run_id=workflow_run.id,
            status=InvestigationStatus.IN_PROGRESS,
        )
        self._db.add(investigation)
        await self._db.flush()

        try:
            # ------------------------------------------------------------------ #
            # 2. Fetch failed jobs and logs
            # ------------------------------------------------------------------ #
            failed_jobs = await self._github.get_failed_jobs(
                installation_id=installation_id,
                owner=owner,
                repo=repo_name,
                run_id=workflow_run.github_run_id,
            )

            if not failed_jobs:
                # No failed jobs found — may have been re-queued or race condition
                logger.warning(
                    "investigation_no_failed_jobs",
                    workflow_run_id=str(workflow_run_id),
                    run_id=workflow_run.github_run_id,
                )
                investigation.status = InvestigationStatus.COMPLETED
                investigation.failure_category = "UNKNOWN"
                investigation.error_summary = "No failed jobs found in this workflow run"
                investigation.confidence = 0.1
                await self._db.flush()
                return investigation

            # ------------------------------------------------------------------ #
            # 3. Download and persist logs for each failed job
            # ------------------------------------------------------------------ #
            all_log_text = ""
            job_records: list[WorkflowJob] = []

            for job in failed_jobs:
                log_text = ""
                try:
                    log_text = await self._github.download_job_logs(
                        installation_id=installation_id,
                        owner=owner,
                        repo=repo_name,
                        job_id=job.id,
                    )
                except Exception as exc:
                    logger.warning(
                        "investigation_log_download_failed",
                        job_id=job.id,
                        error=str(exc),
                    )

                # Persist the job record
                job_record = WorkflowJob(
                    workflow_run_id=workflow_run.id,
                    github_job_id=job.id,
                    name=job.name,
                    status=job.status,
                    conclusion=job.conclusion,
                    started_at=job.started_at,
                    completed_at=job.completed_at,
                    log_text=log_text[:500_000],  # cap at 500KB per job
                    steps=[s.model_dump() for s in job.steps],
                )
                self._db.add(job_record)
                job_records.append(job_record)
                all_log_text += f"\n\n--- Job: {job.name} ---\n{log_text}"

            await self._db.flush()

            # ------------------------------------------------------------------ #
            # 4 & 5. Parse and classify
            # ------------------------------------------------------------------ #
            parsed = parse_log(all_log_text)
            inv_result: InvestigationResult = classify_failure(parsed)

            logger.info(
                "investigation_classified",
                workflow_run_id=str(workflow_run_id),
                category=inv_result.failure_category.value,
                confidence=inv_result.confidence,
                suspected_files=inv_result.suspected_files,
            )

            # ------------------------------------------------------------------ #
            # 6. Update Investigation record
            # ------------------------------------------------------------------ #
            investigation.status = InvestigationStatus.COMPLETED
            investigation.failure_category = inv_result.failure_category.value
            investigation.error_summary = inv_result.error_summary
            investigation.confidence = inv_result.confidence
            investigation.suspected_files = inv_result.suspected_files
            investigation.result = inv_result.to_dict()
            await self._db.flush()

            return investigation

        except Exception as exc:
            logger.error(
                "investigation_failed",
                workflow_run_id=str(workflow_run_id),
                error=str(exc),
            )
            investigation.status = InvestigationStatus.FAILED
            investigation.error_summary = str(exc)[:500]
            await self._db.flush()
            raise
