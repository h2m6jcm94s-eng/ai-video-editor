# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
# Commercial SaaS use is prohibited without written permission.
"""Topaz Video AI API client for Pro-tier upscaling."""

import os
import httpx
from typing import Optional


TOPAZ_API_BASE = "https://api.topazlabs.com/v1"


async def upscale_with_topaz(
    input_path: str,
    output_path: str,
    model: str = "gaia-2",
    scale: int = 2,
) -> str:
    """Upscale video using Topaz Video AI API."""
    api_key = os.environ.get("TOPAZ_API_KEY", "")
    if not api_key:
        raise ValueError("TOPAZ_API_KEY not set")

    async with httpx.AsyncClient() as client:
        # Upload video
        with open(input_path, "rb") as f:
            upload_resp = await client.post(
                f"{TOPAZ_API_BASE}/upload",
                headers={"Authorization": f"Bearer {api_key}"},
                files={"file": f},
            )
        upload_resp.raise_for_status()
        upload_data = upload_resp.json()
        file_id = upload_data["id"]

        # Start job
        job_resp = await client.post(
            f"{TOPAZ_API_BASE}/jobs",
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "input_file_id": file_id,
                "model": model,
                "scale": scale,
            },
        )
        job_resp.raise_for_status()
        job_data = job_resp.json()
        job_id = job_data["id"]

        # Poll for completion
        import asyncio
        while True:
            status_resp = await client.get(
                f"{TOPAZ_API_BASE}/jobs/{job_id}",
                headers={"Authorization": f"Bearer {api_key}"},
            )
            status_data = status_resp.json()
            if status_data["status"] == "completed":
                download_url = status_data["output_url"]
                break
            elif status_data["status"] == "failed":
                raise RuntimeError(f"Topaz job failed: {status_data.get('error', 'Unknown')}")
            await asyncio.sleep(5)

        # Download result
        async with client.stream("GET", download_url) as response:
            response.raise_for_status()
            with open(output_path, "wb") as f:
                async for chunk in response.aiter_bytes():
                    f.write(chunk)

    return output_path
