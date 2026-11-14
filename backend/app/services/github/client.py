"""
GitHub REST API client.

Wraps httpx.AsyncClient with:
- Installation token auth (injected per-call)
- Automatic retry with exponential backoff on 429/5xx
- Rate limit detection and metric tracking
- Structured error logging

Never use this class to make calls with unauthenticated tokens.
All methods accept an installation_id so they can fetch the right token.
"""
from __future__ import annotations

import asyncio
import io
import zipfile
from typing import Any

import httpx

from app.config import get_settings
from app.observability.logging import get_logger
from app.observability.metrics import GITHUB_API_ERRORS, GITHUB_RATE_LIMIT_HITS
from app.services.github.auth import GitHubAppAuth
from app.services.github.models import GitHubWorkflowJob, GitHubWorkflowRun

logger = get_logger(__name__)

_MAX_RETRIES = 5
_RETRY_BACKOFF_BASE = 2.0  # seconds


class GitHubAPIError(Exception):
    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.message = message


class GitHubClient:
    """
    Async GitHub REST API client.

    Create one instance per request context or share at application scope.
    """

    def __init__(self, auth: GitHubAppAuth | None = None) -> None:
        self._auth = auth or GitHubAppAuth()
        self._settings = get_settings()
        self._base_url = str(self._settings.github_api_base_url).rstrip("/")

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #

    def _default_headers(self, token: str) -> dict[str, str]:
        return {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    async def _request(
        self,
        method: str,
        path: str,
        installation_id: int,
        *,
        params: dict | None = None,
        json: dict | None = None,
        raw: bool = False,
    ) -> Any:
        """
        Execute an authenticated request with retry/backoff.

        :param raw: if True, return raw bytes instead of parsed JSON
        """
        url = f"{self._base_url}{path}"

        for attempt in range(_MAX_RETRIES):
            token = await self._auth.get_installation_token(installation_id)
            headers = self._default_headers(token)

            try:
                async with httpx.AsyncClient(timeout=60) as client:
                    response = await client.request(
                        method,
                        url,
                        headers=headers,
                        params=params,
                        json=json,
                        follow_redirects=True,
                    )

                if response.status_code == 429:
                    GITHUB_RATE_LIMIT_HITS.inc()
                    retry_after = int(response.headers.get("Retry-After", "60"))
                    logger.warning(
                        "github_rate_limited",
                        url=url,
                        retry_after=retry_after,
                        attempt=attempt,
                    )
                    await asyncio.sleep(retry_after)
                    continue

                if response.status_code >= 500:
                    GITHUB_API_ERRORS.labels(status_code=str(response.status_code)).inc()
                    backoff = _RETRY_BACKOFF_BASE ** attempt
                    logger.warning(
                        "github_api_server_error",
                        url=url,
                        status_code=response.status_code,
                        attempt=attempt,
                        backoff=backoff,
                    )
                    await asyncio.sleep(backoff)
                    continue

                if not response.is_success:
                    GITHUB_API_ERRORS.labels(status_code=str(response.status_code)).inc()
                    logger.error(
                        "github_api_error",
                        url=url,
                        status_code=response.status_code,
                        body=response.text[:500],
                    )
                    raise GitHubAPIError(
                        status_code=response.status_code,
                        message=f"GitHub API returned {response.status_code}: {response.text[:200]}",
                    )

                return response.content if raw else response.json()

            except httpx.TimeoutException as exc:
                backoff = _RETRY_BACKOFF_BASE ** attempt
                logger.warning(
                    "github_api_timeout",
                    url=url,
                    attempt=attempt,
                    backoff=backoff,
                )
                if attempt == _MAX_RETRIES - 1:
                    raise GitHubAPIError(
                        status_code=0, message=f"Request to {url} timed out after {_MAX_RETRIES} attempts"
                    ) from exc
                await asyncio.sleep(backoff)

        raise GitHubAPIError(status_code=0, message=f"Exhausted {_MAX_RETRIES} retries for {url}")

    # ------------------------------------------------------------------ #
    # Public API methods
    # ------------------------------------------------------------------ #

    async def get_workflow_run(
        self,
        installation_id: int,
        owner: str,
        repo: str,
        run_id: int,
    ) -> GitHubWorkflowRun:
        """Retrieve metadata for a single workflow run."""
        data = await self._request(
            "GET",
            f"/repos/{owner}/{repo}/actions/runs/{run_id}",
            installation_id,
        )
        return GitHubWorkflowRun.model_validate(data)

    async def get_workflow_jobs(
        self,
        installation_id: int,
        owner: str,
        repo: str,
        run_id: int,
    ) -> list[GitHubWorkflowJob]:
        """Retrieve all jobs for a workflow run."""
        data = await self._request(
            "GET",
            f"/repos/{owner}/{repo}/actions/runs/{run_id}/jobs",
            installation_id,
            params={"filter": "latest"},
        )
        return [GitHubWorkflowJob.model_validate(j) for j in data.get("jobs", [])]

    async def get_failed_jobs(
        self,
        installation_id: int,
        owner: str,
        repo: str,
        run_id: int,
    ) -> list[GitHubWorkflowJob]:
        """Return only the jobs that failed or were cancelled."""
        jobs = await self.get_workflow_jobs(installation_id, owner, repo, run_id)
        return [j for j in jobs if j.conclusion in ("failure", "cancelled", "timed_out")]

    async def download_job_logs(
        self,
        installation_id: int,
        owner: str,
        repo: str,
        job_id: int,
    ) -> str:
        """
        Download and return plain-text logs for a single job.

        GitHub returns a redirect to a pre-signed URL; httpx follows it.
        """
        raw = await self._request(
            "GET",
            f"/repos/{owner}/{repo}/actions/jobs/{job_id}/logs",
            installation_id,
            raw=True,
        )
        # Logs are plain text UTF-8
        return raw.decode("utf-8", errors="replace")

    async def download_run_logs(
        self,
        installation_id: int,
        owner: str,
        repo: str,
        run_id: int,
    ) -> dict[str, str]:
        """
        Download the ZIP archive of all run logs and return a dict of
        {filename: log_text}.
        """
        raw = await self._request(
            "GET",
            f"/repos/{owner}/{repo}/actions/runs/{run_id}/logs",
            installation_id,
            raw=True,
        )
        logs: dict[str, str] = {}
        try:
            with zipfile.ZipFile(io.BytesIO(raw)) as zf:
                for name in zf.namelist():
                    if name.endswith(".txt"):
                        with zf.open(name) as f:
                            logs[name] = f.read().decode("utf-8", errors="replace")
        except zipfile.BadZipFile:
            # Some runs return plain text instead of a zip
            logs["run.log"] = raw.decode("utf-8", errors="replace")
        return logs

    async def get_file_contents(
        self,
        installation_id: int,
        owner: str,
        repo: str,
        path: str,
        ref: str,
    ) -> str:
        """
        Retrieve the decoded content of a file at a specific ref.
        Returns empty string if the file doesn't exist (404).
        """
        import base64
        try:
            data = await self._request(
                "GET",
                f"/repos/{owner}/{repo}/contents/{path}",
                installation_id,
                params={"ref": ref},
            )
            if data.get("encoding") == "base64":
                return base64.b64decode(data["content"]).decode("utf-8", errors="replace")
            return data.get("content", "")
        except GitHubAPIError as exc:
            if exc.status_code == 404:
                return ""
            raise

    async def create_branch(
        self,
        installation_id: int,
        owner: str,
        repo: str,
        branch_name: str,
        sha: str,
    ) -> None:
        """Create a new branch pointing at sha."""
        await self._request(
            "POST",
            f"/repos/{owner}/{repo}/git/refs",
            installation_id,
            json={"ref": f"refs/heads/{branch_name}", "sha": sha},
        )
        logger.info(
            "github_branch_created",
            owner=owner,
            repo=repo,
            branch=branch_name,
            sha=sha[:8],
        )

    async def create_pull_request(
        self,
        installation_id: int,
        owner: str,
        repo: str,
        title: str,
        body: str,
        head: str,
        base: str,
    ) -> dict:
        """Open a pull request and return the response payload."""
        data = await self._request(
            "POST",
            f"/repos/{owner}/{repo}/pulls",
            installation_id,
            json={
                "title": title,
                "body": body,
                "head": head,
                "base": base,
            },
        )
        logger.info(
            "github_pr_created",
            owner=owner,
            repo=repo,
            pr_number=data.get("number"),
            url=data.get("html_url"),
        )
        return data
