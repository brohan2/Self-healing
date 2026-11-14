"""
GitHub App authentication.

GitHub Apps authenticate in two steps:
1. Sign a short-lived JWT using the App's RSA private key.
2. Exchange the JWT for a per-installation access token (valid 1 hour).

We cache installation tokens by installation_id with a 5-minute safety
margin before expiry so we never use a token that's about to expire.

Security:
- The private key is never logged.
- Tokens are stored in memory only, never written to disk or DB.
- All values come from settings (environment variables).
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

import jwt

from app.config import get_settings
from app.observability.logging import get_logger

logger = get_logger(__name__)

# Safety buffer: refresh the token this many seconds before it expires
_TOKEN_REFRESH_BUFFER_SECS = 300  # 5 minutes


@dataclass
class InstallationToken:
    token: str
    expires_at: datetime

    def is_valid(self) -> bool:
        """Return True if the token won't expire in the next 5 minutes."""
        remaining = (self.expires_at - datetime.now(timezone.utc)).total_seconds()
        return remaining > _TOKEN_REFRESH_BUFFER_SECS


class GitHubAppAuth:
    """
    Manages GitHub App JWT and per-installation access tokens.

    Usage:
        auth = GitHubAppAuth()
        token = await auth.get_installation_token(installation_id)
        headers = {"Authorization": f"token {token}"}
    """

    def __init__(self) -> None:
        self._settings = get_settings()
        self._token_cache: dict[int, InstallationToken] = {}

    def _generate_app_jwt(self) -> str:
        """
        Generate a signed JWT for the GitHub App itself.

        Valid for 10 minutes (GitHub max is 10 minutes).
        """
        now = int(time.time())
        payload = {
            "iat": now - 60,       # issued-at: 60s in the past to tolerate clock skew
            "exp": now + 9 * 60,   # expires in 9 minutes
            "iss": self._settings.github_app_id,
        }
        try:
            token = jwt.encode(
                payload,
                self._settings.github_app_private_key,
                algorithm="RS256",
            )
            logger.debug("github_app_jwt_generated", app_id=self._settings.github_app_id)
            return token
        except Exception as exc:
            logger.error("github_app_jwt_generation_failed", error=str(exc))
            raise

    async def get_installation_token(
        self,
        installation_id: int,
        http_client=None,
    ) -> str:
        """
        Return a valid installation access token, fetching a new one if needed.

        :param installation_id: GitHub App installation ID
        :param http_client: optional pre-built httpx.AsyncClient; if None a new one is created
        """
        cached = self._token_cache.get(installation_id)
        if cached and cached.is_valid():
            logger.debug(
                "github_installation_token_cache_hit",
                installation_id=installation_id,
            )
            return cached.token

        token, expires_at = await self._fetch_installation_token(
            installation_id, http_client
        )
        self._token_cache[installation_id] = InstallationToken(
            token=token, expires_at=expires_at
        )
        logger.info(
            "github_installation_token_fetched",
            installation_id=installation_id,
            expires_at=expires_at.isoformat(),
        )
        return token

    async def _fetch_installation_token(
        self,
        installation_id: int,
        http_client=None,
    ) -> tuple[str, datetime]:
        """Call the GitHub API to exchange app JWT for installation token."""
        import httpx

        app_jwt = self._generate_app_jwt()
        url = (
            f"{self._settings.github_api_base_url}"
            f"/app/installations/{installation_id}/access_tokens"
        )
        headers = {
            "Authorization": f"Bearer {app_jwt}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

        close_client = False
        if http_client is None:
            http_client = httpx.AsyncClient(timeout=30)
            close_client = True

        try:
            response = await http_client.post(url, headers=headers)
            response.raise_for_status()
            data = response.json()

            token = data["token"]
            expires_at = datetime.fromisoformat(
                data["expires_at"].replace("Z", "+00:00")
            )
            return token, expires_at
        finally:
            if close_client:
                await http_client.aclose()
