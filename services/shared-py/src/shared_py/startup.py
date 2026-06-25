# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
# Commercial SaaS use is prohibited without written permission.
"""Startup validation for Python workers."""

import os
import sys

from shared_py.logging_config import StructuredLogger

logger = StructuredLogger("startup")

REQUIRED = {
    "R2_ENDPOINT": "Cloudflare R2 / S3 endpoint URL",
    "R2_ACCESS_KEY_ID": "R2 access key",
    "R2_SECRET_ACCESS_KEY": "R2 secret key",
    "R2_BUCKET_NAME": "R2 bucket name",
    "REDIS_URL": "Redis connection URL",
    "DATABASE_URL": "PostgreSQL connection URL",
    "INTERNAL_WORKER_TOKEN": "internal API token used by workers",
}

OPTIONAL_BUT_RECOMMENDED = {
    "TWELVELABS_API_KEY": "Twelve Labs / Marengo API key (clip semantic scoring)",
}

AI_PROVIDER_KEYS = {
    "claude": "ANTHROPIC_API_KEY",
    "gemini": "GOOGLE_API_KEY",
    "groq": "GROQ_API_KEY",
    "openai": "OPENAI_API_KEY",
    "kimi": "KIMI_API_KEY",
    "qwen": "QWEN_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
}


def validate_startup(worker_name: str) -> None:
    missing = [f"{k} ({desc})" for k, desc in REQUIRED.items() if not os.environ.get(k)]
    if missing:
        logger.error(
            f"WORKER '{worker_name}' CANNOT START — missing env vars",
            missing=missing,
            hint="Copy infra/.env.example → .env and fill values",
        )
        sys.exit(1)

    missing_optional = [f"{k} ({desc})" for k, desc in OPTIONAL_BUT_RECOMMENDED.items() if not os.environ.get(k)]
    if missing_optional:
        logger.warning(
            f"WORKER '{worker_name}' starting without recommended env vars",
            missing=missing_optional,
        )

    # Warn about AI provider chain
    provider_chain = os.environ.get("AI_PROVIDER", "programmatic").split(",")
    for provider in provider_chain:
        provider = provider.strip()
        key_name = AI_PROVIDER_KEYS.get(provider)
        if key_name and not os.environ.get(key_name):
            logger.warning(
                f"AI provider '{provider}' in chain but key is not set — will skip",
                provider=provider,
                key_name=key_name,
            )
