"""
Unit tests for WebhookVerifier.

These are pure logic tests with no network or DB involvement.
"""
from __future__ import annotations

import hashlib
import hmac

import pytest

from app.services.github.webhook_verifier import WebhookVerifier

SECRET = "supersecret"
PAYLOAD = b'{"action": "completed"}'


def _valid_sig(payload: bytes = PAYLOAD, secret: str = SECRET) -> str:
    sig = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    return f"sha256={sig}"


class TestWebhookVerifier:
    def test_valid_signature_returns_true(self) -> None:
        verifier = WebhookVerifier(secret=SECRET)
        assert verifier.verify(PAYLOAD, _valid_sig()) is True

    def test_wrong_secret_returns_false(self) -> None:
        verifier = WebhookVerifier(secret="wrong_secret")
        assert verifier.verify(PAYLOAD, _valid_sig()) is False

    def test_tampered_payload_returns_false(self) -> None:
        verifier = WebhookVerifier(secret=SECRET)
        assert verifier.verify(b'{"action": "tampered"}', _valid_sig()) is False

    def test_missing_header_returns_false(self) -> None:
        verifier = WebhookVerifier(secret=SECRET)
        assert verifier.verify(PAYLOAD, None) is False

    def test_empty_header_returns_false(self) -> None:
        verifier = WebhookVerifier(secret=SECRET)
        assert verifier.verify(PAYLOAD, "") is False

    def test_malformed_header_no_prefix_returns_false(self) -> None:
        verifier = WebhookVerifier(secret=SECRET)
        # Missing "sha256=" prefix
        sig = hmac.new(SECRET.encode(), PAYLOAD, hashlib.sha256).hexdigest()
        assert verifier.verify(PAYLOAD, sig) is False

    def test_different_payloads_different_signatures(self) -> None:
        verifier = WebhookVerifier(secret=SECRET)
        sig_a = _valid_sig(b"payload_a")
        assert verifier.verify(b"payload_b", sig_a) is False

    def test_empty_payload_with_correct_signature(self) -> None:
        verifier = WebhookVerifier(secret=SECRET)
        empty = b""
        sig = _valid_sig(empty)
        assert verifier.verify(empty, sig) is True
