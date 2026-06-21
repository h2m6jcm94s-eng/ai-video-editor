# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
# Commercial SaaS use is prohibited without written permission.
"""Temporal activities for the render worker."""

import os
import tempfile
from typing import Dict, List, Optional

import httpx
from temporalio import activity

from render_worker.compiler import compile_timeline
from shared_py.config import settings
from shared_py.models import CutList, RenderConfig
from shared_py.storage import download_asset, get_presigned_download_url, upload_file


def _internal_headers() -> Dict[str, str]:
    token = os.environ.get("INTERNAL_WORKER_TOKEN")
    if not token:
        raise RuntimeError("INTERNAL_WORKER_TOKEN not set")
    return {"x-internal-token": token}


@activity.defn
async def fetch_project(project_id: str) -> dict:
    """Fetch project details from the internal API."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{settings.api_base}/internal/projects/{project_id}",
            headers=_internal_headers(),
            timeout=30,
        )
    resp.raise_for_status()
    return resp.json()


def _activity_run_id() -> str:
    try:
        return activity.info().workflow_run_id or "0"
    except RuntimeError:
        return "0"


@activity.defn
async def download_render_assets(asset_ids: List[str], asset_key_map: Dict[str, str]) -> Dict[str, str]:
    """Download required assets to local temp paths."""
    local_paths: Dict[str, str] = {}
    for asset_id in asset_ids:
        storage_key = asset_key_map.get(asset_id)
        if not storage_key:
            activity.logger.warning(f"No storage key for asset {asset_id}, skipping download")
            continue
        ext = os.path.splitext(storage_key)[1] or ".tmp"
        local_path = os.path.join(tempfile.gettempdir(), f"ave_{asset_id}_{_activity_run_id()}{ext}")
        local_paths[asset_id] = download_asset(storage_key, local_path)
    return local_paths


@activity.defn
async def compile_render(
    cutlist: dict,
    local_paths: Dict[str, str],
    song_asset_id: Optional[str] = None,
    reference_asset_id: Optional[str] = None,
) -> str:
    """Compile the cut-list into a final MP4."""
    cutlist_obj = CutList(**cutlist)

    # Map slots to local clip paths
    clip_paths: Dict[str, str] = {}
    for slot in cutlist_obj.slots:
        clip_id = slot.selected_clip_id
        if clip_id and clip_id in local_paths:
            clip_paths[clip_id] = local_paths[clip_id]

    # Resolve song path if available
    song_path = local_paths.get(song_asset_id) if song_asset_id else None

    output_path = os.path.join(
        tempfile.gettempdir(),
        f"ave_render_{cutlist_obj.globals.total_duration_s:.0f}s_{_activity_run_id()}.mp4",
    )

    config = RenderConfig(
        output_path=output_path,
        width=720,
        height=1280,
        fps=30,
        video_codec="libx264",
        video_preset="slow",
        video_crf=23,
        audio_codec="aac",
        audio_bitrate="192k",
        pix_fmt="yuv420p",
        song_path=song_path,
    )

    compile_timeline(cutlist_obj, clip_paths, output_path, config)
    return output_path


@activity.defn
async def upload_render(output_path: str, project_id: str, render_id: str) -> dict:
    """Upload rendered MP4 to R2 and create an asset row via the internal API."""
    filename = os.path.basename(output_path)

    async with httpx.AsyncClient() as client:
        # Create asset row first so the API knows about it
        create_resp = await client.post(
            f"{settings.api_base}/internal/assets",
            json={
                "projectId": project_id,
                "type": "render",
                "filename": filename,
                "mimeType": "video/mp4",
            },
            headers=_internal_headers(),
            timeout=30,
        )
        create_resp.raise_for_status()
        asset_data = create_resp.json()
        asset_id = asset_data["assetId"]
        asset_storage_key = asset_data["storageKey"]

        # Upload to R2 using the API-provided storage key
        upload_file(output_path, asset_storage_key, content_type="video/mp4")

        # Generate a presigned download URL and mark the asset complete
        size_bytes = os.path.getsize(output_path)
        storage_url = get_presigned_download_url(asset_storage_key, expires_in=3600)

        complete_resp = await client.patch(
            f"{settings.api_base}/internal/assets/{asset_id}/complete",
            json={
                "sizeBytes": size_bytes,
                "storageUrl": storage_url,
            },
            headers=_internal_headers(),
            timeout=30,
        )
        complete_resp.raise_for_status()

    return {"asset_id": asset_id, "storage_key": asset_storage_key}


@activity.defn
async def complete_render(render_id: str, output_asset_id: str, completion_token: Optional[str] = None) -> None:
    """Mark the render job as complete."""
    payload = {
        "status": "complete",
        "outputAssetId": output_asset_id,
    }
    if completion_token:
        payload["completionToken"] = completion_token
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{settings.api_base}/renders/{render_id}/complete",
            json=payload,
            headers=_internal_headers(),
            timeout=30,
        )
    resp.raise_for_status()


@activity.defn
async def cleanup_render_assets(local_paths: Dict[str, str], output_path: Optional[str] = None) -> None:
    """Remove downloaded source assets and the rendered output from the local filesystem."""
    for path in list(local_paths.values()):
        try:
            if path and os.path.exists(path):
                os.remove(path)
        except OSError as e:
            activity.logger.warning(f"Failed to remove local asset {path}: {e}")

    if output_path:
        try:
            if os.path.exists(output_path):
                os.remove(output_path)
        except OSError as e:
            activity.logger.warning(f"Failed to remove render output {output_path}: {e}")
