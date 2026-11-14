"""
Prometheus metrics definitions.

Import REGISTRY counters/histograms from this module rather than
creating them ad-hoc in business logic.
"""
from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram

# ------------------------------------------------------------------ #
# Webhook ingestion
# ------------------------------------------------------------------ #
WEBHOOKS_RECEIVED = Counter(
    "autofix_webhooks_received_total",
    "Total GitHub webhook events received",
    ["event_type"],
)

WEBHOOKS_INVALID_SIGNATURE = Counter(
    "autofix_webhooks_invalid_signature_total",
    "Webhook events rejected due to invalid HMAC signature",
)

WEBHOOKS_DUPLICATE = Counter(
    "autofix_webhooks_duplicate_total",
    "Duplicate webhook deliveries (idempotency hits)",
)

# ------------------------------------------------------------------ #
# Repairs
# ------------------------------------------------------------------ #
REPAIRS_ATTEMPTED = Counter(
    "autofix_repairs_attempted_total",
    "Total repair attempts initiated",
    ["repository"],
)

REPAIRS_SUCCEEDED = Counter(
    "autofix_repairs_succeeded_total",
    "Repairs that produced a validated patch and opened a PR",
    ["repository"],
)

REPAIRS_FAILED = Counter(
    "autofix_repairs_failed_total",
    "Repairs that exhausted all retry attempts without success",
    ["repository"],
)

REPAIRS_ESCALATED = Counter(
    "autofix_repairs_escalated_total",
    "Repairs escalated for human review",
    ["repository"],
)

# ------------------------------------------------------------------ #
# AI usage
# ------------------------------------------------------------------ #
AI_TOKENS_USED = Counter(
    "autofix_ai_tokens_used_total",
    "LLM tokens consumed",
    ["provider", "model", "token_type"],
)

AI_AGENT_ITERATIONS = Histogram(
    "autofix_ai_agent_iterations",
    "Number of tool-call iterations per agent run",
    buckets=[1, 2, 3, 5, 8, 10, 15, 20],
)

# ------------------------------------------------------------------ #
# Sandbox execution
# ------------------------------------------------------------------ #
SANDBOX_DURATION = Histogram(
    "autofix_sandbox_duration_seconds",
    "Wall-clock seconds for sandbox execution",
    buckets=[5, 10, 30, 60, 120, 180, 300, 600],
)

SANDBOX_TIMEOUT = Counter(
    "autofix_sandbox_timeout_total",
    "Sandbox executions that exceeded the timeout limit",
)

# ------------------------------------------------------------------ #
# GitHub API
# ------------------------------------------------------------------ #
GITHUB_API_ERRORS = Counter(
    "autofix_github_api_errors_total",
    "GitHub API errors by status code",
    ["status_code"],
)

GITHUB_RATE_LIMIT_HITS = Counter(
    "autofix_github_rate_limit_hits_total",
    "Times GitHub API rate limit was hit (429)",
)

# ------------------------------------------------------------------ #
# Queue
# ------------------------------------------------------------------ #
QUEUE_BACKLOG = Gauge(
    "autofix_queue_backlog",
    "Pending messages in a Redis stream",
    ["stream"],
)
