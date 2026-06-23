#!/usr/bin/env python3
"""Lightweight health checks for third-party API keys defined in the environment.

Run from the repo root, e.g.:
    uv run python scripts/check_external_apis.py

The script only reports whether each service responded with a working-auth status.
No keys or response bodies are printed.
"""

import os
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv


def load_env() -> None:
    repo_root = Path(__file__).resolve().parent.parent
    for name in (".env.local", ".env"):
        path = repo_root / "apps" / "api" / name
        if path.exists():
            load_dotenv(path, override=True)
        path = repo_root / name
        if path.exists():
            load_dotenv(path, override=False)


def check(label: str, method: str, url: str, **kwargs) -> dict:
    try:
        resp = requests.request(method, url, timeout=20, **kwargs)
        ok = resp.status_code in (200, 201, 202)
        # Treat 401/403 as "key rejected / expired" and anything else as unexpected.
        if resp.status_code in (401, 403):
            status = "KEY_REJECTED"
        elif resp.status_code == 429:
            status = "RATE_LIMITED"
        elif ok:
            status = "OK"
        else:
            status = f"HTTP_{resp.status_code}"
        return {"label": label, "status": status, "detail": ""}
    except requests.exceptions.Timeout:
        return {"label": label, "status": "TIMEOUT", "detail": ""}
    except Exception as exc:
        return {"label": label, "status": "ERROR", "detail": str(exc)}


def main() -> int:
    load_env()
    results: list[dict] = []

    # AI / media generation
    if key := os.getenv("ELEVENLABS_API_KEY"):
        results.append(check(
            "ElevenLabs",
            "GET",
            "https://api.elevenlabs.io/v1/models",
            headers={"xi-api-key": key},
        ))

    gemini_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if gemini_key:
        results.append(check(
            "Gemini / Google",
            "GET",
            f"https://generativelanguage.googleapis.com/v1beta/models?key={gemini_key}",
        ))

    if key := os.getenv("GROQ_API_KEY"):
        results.append(check(
            "Groq",
            "GET",
            "https://api.groq.com/openai/v1/models",
            headers={"Authorization": f"Bearer {key}"},
        ))

    if key := os.getenv("KIMI_API_KEY"):
        results.append(check(
            "Kimi (Moonshot)",
            "GET",
            "https://api.moonshot.cn/v1/models",
            headers={"Authorization": f"Bearer {key}"},
        ))

    if key := os.getenv("KLING_API_KEY"):
        # Kling does not publish a simple GET health endpoint; try the v1 base.
        results.append(check(
            "Kling",
            "GET",
            "https://api.klingai.com/v1/",
            headers={"Authorization": f"Bearer {key}"},
        ))

    if key := os.getenv("PEXELS_API_KEY"):
        results.append(check(
            "Pexels",
            "GET",
            "https://api.pexels.com/v1/curated?per_page=1",
            headers={"Authorization": key},
        ))

    if key := os.getenv("SEEDANCE_API_KEY"):
        # Seedance (ByteDance) base URL; no public health endpoint documented.
        results.append(check(
            "Seedance",
            "GET",
            "https://api.seedance.io/v1/",
            headers={"Authorization": f"Bearer {key}"},
        ))

    if key := os.getenv("TWELVELABS_API_KEY"):
        results.append(check(
            "TwelveLabs",
            "GET",
            "https://api.twelvelabs.io/v1.1/",
            headers={"x-api-key": key},
        ))

    if key := os.getenv("FREESOUND_API_TOKEN"):
        results.append(check(
            "Freesound",
            "GET",
            "https://freesound.org/apiv2/search/text/",
            params={"query": "test", "token": key, "fields": "id"},
        ))

    # Auth / storage
    if key := os.getenv("CLERK_SECRET_KEY"):
        results.append(check(
            "Clerk",
            "GET",
            "https://api.clerk.com/v1/users?limit=1",
            headers={"Authorization": f"Bearer {key}"},
        ))

    # R2 / S3-compatible storage
    r2_key = os.getenv("R2_ACCESS_KEY_ID")
    r2_secret = os.getenv("R2_SECRET_ACCESS_KEY")
    r2_endpoint = os.getenv("R2_ENDPOINT")
    r2_bucket = os.getenv("R2_BUCKET_NAME")
    if r2_key and r2_secret and r2_endpoint and r2_bucket:
        try:
            import boto3
            s3 = boto3.client(
                "s3",
                endpoint_url=r2_endpoint,
                aws_access_key_id=r2_key,
                aws_secret_access_key=r2_secret,
            )
            s3.head_bucket(Bucket=r2_bucket)
            results.append({"label": "R2 Storage", "status": "OK", "detail": ""})
        except Exception as exc:
            results.append({"label": "R2 Storage", "status": "ERROR", "detail": str(exc)})

    # Redis
    redis_url = os.getenv("REDIS_URL")
    if redis_url:
        try:
            import redis
            client = redis.from_url(redis_url, socket_connect_timeout=5)
            client.ping()
            results.append({"label": "Redis", "status": "OK", "detail": ""})
        except Exception as exc:
            results.append({"label": "Redis", "status": "ERROR", "detail": str(exc)})

    # Temporal (gRPC connectivity only; no key required for local dev)
    temporal_host = os.getenv("TEMPORAL_HOST")
    if temporal_host:
        try:
            from temporalio.client import Client
            import asyncio
            asyncio.run(Client.connect(temporal_host))
            results.append({"label": "Temporal", "status": "OK", "detail": ""})
        except Exception as exc:
            results.append({"label": "Temporal", "status": "ERROR", "detail": str(exc)})

    print(f"{'Service':<20} {'Status':<15} Detail")
    print("-" * 60)
    failures = []
    for r in results:
        detail = r["detail"][:60] if r["detail"] else ""
        print(f"{r['label']:<20} {r['status']:<15} {detail}")
        if r["status"] not in {"OK", "RATE_LIMITED"}:
            failures.append(r["label"])

    print("-" * 60)
    if failures:
        print(f"Potentially unhealthy services: {', '.join(failures)}")
        return 1
    print("All reachable services reported OK.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
