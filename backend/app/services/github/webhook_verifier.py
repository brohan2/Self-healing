"""
GitHub webhook HMAC-SHA256 signature verifier.

GitHub signs every webhook payload with the secret you configured in the
App settings.  The signature arrives in the X-Hub-Signature-256 header as
"sha256=<hex-digest>".

Security note: comparison uses hmac.compare_digest to avoid timing attacks.
"""
from __future__ import annotations

import hashlib
import hmac

from app.config import get_settings
from app.observability.logging import get_logger

logger = get_logger(__name__)


class WebhookVerifier:
    """Verifies the HMAC-SHA256 signature on GitHub webhook payloads."""

    def __init__(self, secret: str | None = None) -> None:
        settings = get_settings()
        self._secret = (secret or settings.github_webhook_secret).encode("utf-8")

    def verify(self, payload: bytes, signature_header: str | None) -> bool:
        """
        Return True if the payload's HMAC matches the header.

        :param payload: raw request body bytes
        :param signature_header: value of X-Hub-Signature-256 header
        """
        if not signature_header:
            logger.warning("webhook_signature_header_missing")
            return False

        if not signature_header.startswith("sha256="):
            logger.warning(
                "webhook_signature_header_malformed",
                header=signature_header[:20],
            )
            return False

        expected_sig = signature_header[len("sha256="):]
        computed_sig = hmac.new(self._secret, payload, hashlib.sha256).hexdigest()

        match = hmac.compare_digest(computed_sig, expected_sig)
        if not match:
            logger.warning("webhook_signature_mismatch")
        return match
