# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 — see LICENSE in the repo root.
"""Guardrails service configuration."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Service settings loaded from environment."""

    host: str = "0.0.0.0"
    port: int = 8000
    log_level: str = "info"
    guardrails_enabled: bool = True
    # Timeout for guardrail evaluation (seconds)
    eval_timeout: float = 3.0
    # Fail-open: if True, allow requests when guardrails fail internally
    fail_open: bool = True

    class Config:
        env_prefix = "GUARDRAILS_"
        case_sensitive = False


settings = Settings()
