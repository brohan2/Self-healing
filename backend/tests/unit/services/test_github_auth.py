"""
Unit tests for GitHubAppAuth.

Mocks the HTTP call so no real GitHub App credentials are needed.
"""
from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.github.auth import GitHubAppAuth, InstallationToken


class TestInstallationTokenValidity:
    def test_valid_token_returns_true(self) -> None:
        # Expires far in the future
        future = datetime.now(timezone.utc) + timedelta(hours=1)
        token = InstallationToken(token="tok", expires_at=future)
        assert token.is_valid() is True

    def test_soon_expiring_token_returns_false(self) -> None:
        # Expires in 60 seconds — within the 5-minute buffer
        soon = datetime.now(timezone.utc) + timedelta(seconds=60)
        token = InstallationToken(token="tok", expires_at=soon)
        assert token.is_valid() is False

    def test_expired_token_returns_false(self) -> None:
        past = datetime.now(timezone.utc) - timedelta(hours=1)
        token = InstallationToken(token="tok", expires_at=past)
        assert token.is_valid() is False


class TestGitHubAppAuth:
    @pytest.mark.asyncio
    async def test_cache_hit_skips_http_call(self) -> None:
        """If a valid token is cached, no HTTP call should be made."""
        auth = GitHubAppAuth()
        future = datetime.now(timezone.utc) + timedelta(hours=1)
        auth._token_cache[999] = InstallationToken(token="cached-token", expires_at=future)

        token = await auth.get_installation_token(installation_id=999)
        assert token == "cached-token"

    @pytest.mark.asyncio
    async def test_fetch_called_when_no_cache(self) -> None:
        """When no cache entry exists, _fetch_installation_token is called."""
        auth = GitHubAppAuth()
        future = datetime.now(timezone.utc) + timedelta(hours=1)

        with patch.object(
            auth,
            "_fetch_installation_token",
            new_callable=AsyncMock,
            return_value=("new-token", future),
        ) as mock_fetch:
            token = await auth.get_installation_token(installation_id=42)
            mock_fetch.assert_called_once_with(42, None)
            assert token == "new-token"

    @pytest.mark.asyncio
    async def test_stale_cache_triggers_refresh(self) -> None:
        """A nearly-expired token should be refreshed."""
        auth = GitHubAppAuth()
        # Token expires in 60 seconds — below the 5-minute buffer
        soon = datetime.now(timezone.utc) + timedelta(seconds=60)
        auth._token_cache[77] = InstallationToken(token="old-token", expires_at=soon)

        future = datetime.now(timezone.utc) + timedelta(hours=1)
        with patch.object(
            auth,
            "_fetch_installation_token",
            new_callable=AsyncMock,
            return_value=("refreshed-token", future),
        ) as mock_fetch:
            token = await auth.get_installation_token(installation_id=77)
            mock_fetch.assert_called_once()
            assert token == "refreshed-token"
