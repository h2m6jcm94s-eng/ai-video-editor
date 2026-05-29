"""Startup validation for Python workers."""

import os
import sys

REQUIRED = {
    "R2_ENDPOINT": "Cloudflare R2 / S3 endpoint URL",
    "R2_ACCESS_KEY_ID": "R2 access key",
    "R2_SECRET_ACCESS_KEY": "R2 secret key",
    "R2_BUCKET_NAME": "R2 bucket name",
    "REDIS_URL": "Redis connection URL",
    "DATABASE_URL": "PostgreSQL connection URL",
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
        print(f"\n{'═'*60}")
        print(f"  WORKER '{worker_name}' CANNOT START — missing env vars:")
        for m in missing:
            print(f"  ✗  {m}")
        print(f"  Copy infra/.env.example → .env and fill values")
        print(f"{'═'*60}\n")
        sys.exit(1)

    # Warn about AI provider chain
    provider_chain = os.environ.get("AI_PROVIDER", "programmatic").split(",")
    for provider in provider_chain:
        provider = provider.strip()
        key_name = AI_PROVIDER_KEYS.get(provider)
        if key_name and not os.environ.get(key_name):
            print(f"  ⚠  AI provider '{provider}' in chain but {key_name} is not set — will skip")
