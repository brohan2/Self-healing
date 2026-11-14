"""
Application configuration.

All values are driven by environment variables.  No defaults contain secrets.
Sensitive values are marked with `repr=False` to prevent accidental logging.
"""
from __future__ import annotations

from enum import StrEnum
from functools import lru_cache
from typing import Annotated

from pydantic import AnyHttpUrl, Field, PostgresDsn, RedisDsn, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(StrEnum):
    DEVELOPMENT = "development"
    TESTING = "testing"
    PRODUCTION = "production"


class LogLevel(StrEnum):
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ------------------------------------------------------------------ #
    # Application
    # ------------------------------------------------------------------ #
    app_name: str = "AutoFix AI"
    environment: Environment = Environment.DEVELOPMENT
    debug: bool = False
    log_level: LogLevel = LogLevel.INFO

    # ------------------------------------------------------------------ #
    # API
    # ------------------------------------------------------------------ #
    api_v1_prefix: str = "/api/v1"
    allowed_origins: list[str] = ["http://localhost:3000"]

    # ------------------------------------------------------------------ #
    # Database
    # ------------------------------------------------------------------ #
    database_url: Annotated[
        PostgresDsn,
        Field(description="Async PostgreSQL DSN (asyncpg driver)"),
    ]

    database_pool_size: int = 10
    database_max_overflow: int = 20
    database_pool_timeout: int = 30

    # ------------------------------------------------------------------ #
    # Redis
    # ------------------------------------------------------------------ #
    redis_url: Annotated[
        RedisDsn,
        Field(description="Redis DSN", default="redis://localhost:6379/0"),
    ] = "redis://localhost:6379/0"  # type: ignore[assignment]

    redis_stream_webhooks: str = "autofix:webhooks"
    redis_stream_investigations: str = "autofix:investigations"
    redis_stream_repairs: str = "autofix:repairs"
    redis_consumer_group: str = "autofix-workers"

    # ------------------------------------------------------------------ #
    # GitHub App
    # ------------------------------------------------------------------ #
    github_app_id: str = "placeholder"
    github_app_private_key: Annotated[
        str,
        Field(repr=False, description="PEM-encoded RSA private key for the GitHub App"),
    ] = "placeholder"
    github_webhook_secret: Annotated[
        str,
        Field(repr=False, description="Secret used to verify webhook signatures"),
    ] = "placeholder"
    github_api_base_url: AnyHttpUrl = "https://api.github.com"  # type: ignore[assignment]

    # ------------------------------------------------------------------ #
    # AI Provider
    # ------------------------------------------------------------------ #
    ai_provider: str = "openai"
    ai_api_key: Annotated[
        str,
        Field(repr=False, description="LLM API key"),
    ] = ""
    ai_model: str = "gpt-4o"
    ai_max_tokens: int = 4096
    ai_temperature: float = 0.1
    ai_max_agent_iterations: int = 10

    # ------------------------------------------------------------------ #
    # Sandbox / Docker
    # ------------------------------------------------------------------ #
    sandbox_docker_image: str = "autofix-ai/sandbox:latest"
    sandbox_cpu_quota: int = 100_000   # 100% of one CPU
    sandbox_mem_limit: str = "512m"
    sandbox_timeout_seconds: int = 300
    sandbox_network_mode: str = "none"
    sandbox_work_dir: str = "/tmp/autofix-sandbox"  # noqa: S108

    # ------------------------------------------------------------------ #
    # Repair Orchestrator
    # ------------------------------------------------------------------ #
    max_repair_attempts: int = 3
    worker_crash_recovery_minutes: int = 10

    # ------------------------------------------------------------------ #
    # Observability
    # ------------------------------------------------------------------ #
    otel_enabled: bool = False
    otel_exporter_otlp_endpoint: str = "http://localhost:4317"
    prometheus_enabled: bool = True

    # ------------------------------------------------------------------ #
    # Validators
    # ------------------------------------------------------------------ #
    @field_validator("github_app_private_key", mode="before")
    @classmethod
    def replace_literal_newlines(cls, v: str) -> str:
        """Allow \\n-escaped newlines from environment variables."""
        return v.replace("\\n", "\n") if isinstance(v, str) else v


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached Settings instance.  Import and call this everywhere."""
    return Settings()  # type: ignore[call-arg]
