#!/usr/bin/env python3
# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
# Commercial SaaS use is prohibited without written permission.
"""Verify that all environment variables and external services are reachable."""

import asyncio
import os
import sys
from pathlib import Path

import boto3
import httpx
import redis
from botocore.config import Config
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent

REQUIRED = [
    ("R2_ENDPOINT", "R2 / S3 endpoint"),
    ("R2_ACCESS_KEY_ID", "R2 access key"),
    ("R2_SECRET_ACCESS_KEY", "R2 secret key"),
    ("R2_BUCKET_NAME", "R2 bucket name"),
    ("REDIS_URL", "Redis URL"),
    ("DATABASE_URL", "PostgreSQL URL"),
    ("INTERNAL_WORKER_TOKEN", "internal API token"),
    ("TWELVELABS_API_KEY", "Twelve Labs / Marengo API key"),
]


def _load_env() -> None:
    env_local = ROOT / "apps" / "api" / ".env.local"
    if env_local.exists():
        load_dotenv(env_local, override=False)


def _check_env() -> list[str]:
    missing = []
    for key, desc in REQUIRED:
        if not os.environ.get(key):
            missing.append(f"  - {key} ({desc})")
    return missing


async def _check_marengo() -> str:
    try:
        from reason_worker.marengo_client import MarengoClient

        client = MarengoClient()
        if not client.available():
            return " Marengo client not available (missing key or SDK?)"
        emb = client.embed_text("verification prompt")
        if emb is None:
            return " Marengo text embedding returned None"
        if len(emb) != 512:
            return f" Marengo embedding dimension is {len(emb)}, expected 512"
        return " OK (512-dim embedding)"
    except Exception as e:
        return f" FAILED: {e}"


async def _check_temporal() -> str:
    try:
        from temporalio.client import Client

        host = os.environ.get("TEMPORAL_HOST", "localhost:7233")
        namespace = os.environ.get("TEMPORAL_NAMESPACE", "default")
        await Client.connect(host, namespace=namespace)
        return " OK"
    except Exception as e:
        return f" FAILED: {e}"


def _check_redis() -> str:
    try:
        url = os.environ.get("REDIS_URL", "redis://localhost:6379")
        r = redis.from_url(url, decode_responses=True)
        r.ping()
        return " OK"
    except Exception as e:
        return f" FAILED: {e}"


def _check_r2() -> str:
    try:
        endpoint = os.environ.get("R2_ENDPOINT")
        s3 = boto3.client(
            "s3",
            endpoint_url=endpoint,
            aws_access_key_id=os.environ.get("R2_ACCESS_KEY_ID"),
            aws_secret_access_key=os.environ.get("R2_SECRET_ACCESS_KEY"),
            config=Config(signature_version="s3v4"),
        )
        s3.list_buckets()
        return " OK"
    except Exception as e:
        return f" FAILED: {e}"


def _check_api_ready() -> str:
    try:
        api_base = os.environ.get("API_BASE", "http://localhost:4000/api")
        with httpx.Client(timeout=10) as client:
            resp = client.get(f"{api_base}/health/ready")
        if resp.status_code == 200:
            data = resp.json()
            status = data.get("status", "unknown")
            return f" OK (status: {status})"
        return f" HTTP {resp.status_code}: {resp.text[:200]}"
    except Exception as e:
        return f" FAILED: {e}"


async def main() -> int:
    _load_env()

    print("Checking environment and service connectivity...\n")

    missing = _check_env()
    if missing:
        print("Missing required environment variables:")
        for line in missing:
            print(line)
        print(f"\nHint: fill values in {ROOT / 'apps' / 'api' / '.env.local'}")
        return 1

    print("Environment variables: OK")

    print(f"Marengo (Twelve Labs):{await _check_marengo()}")
    print(f"Temporal:            {await _check_temporal()}")
    print(f"Redis:               {_check_redis()}")
    print(f"R2 / S3:             {_check_r2()}")
    print(f"API ready check:     {_check_api_ready()}")

    print("\nVerification complete.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
