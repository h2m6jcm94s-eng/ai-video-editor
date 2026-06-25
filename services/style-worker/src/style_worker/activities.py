# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
# Commercial SaaS use is prohibited without written permission.
"""Temporal activities for the style-analysis worker."""

import os
import shutil
import tempfile
from typing import Dict, List, Optional

import httpx
from temporalio import activity

from style_worker.camera_motion import analyze_camera_motion
from style_worker.lut_extract import extract_lut_from_reference
from style_worker.text_extract import extract_text_overlays
from style_worker.transition_type import classify_transitions
from shared_py.config import settings
from shared_py.models import Overlay, ShotBoundary, StyleAnalysis
from shared_py.storage import download_asset, get_presigned_download_url, upload_file


def _internal_headers() -> Dict[str, str]:
    token = os.environ.get("INTERNAL_WORKER_TOKEN")
    if not token:
        raise RuntimeError("INTERNAL_WORKER_TOKEN not set")
    return {"x-internal-token": token}


def _activity_run_id() -> str:
    try:
        return activity.info().workflow_run_id or "0"
    except RuntimeError:
        return "0"


@activity.defn
async def download_reference_video(asset_id: str, storage_key: str) -> str:
    """Download a reference video asset from object storage to a local path."""
    ext = os.path.splitext(storage_key)[1] or ".mp4"
    local_path = os.path.join(
        tempfile.gettempdir(),
        f"ave_style_{asset_id}_{_activity_run_id()}{ext}",
    )
    return download_asset(storage_key, local_path)


@activity.defn
async def extract_lut(
    video_path: str,
    output_dir: str,
    strength: float = 0.5,
    project_id: str = "",
) -> dict:
    """Extract a .cube LUT from a reference video and persist it to R2."""
    if not output_dir:
        output_dir = tempfile.mkdtemp(prefix="ave_style_")
    cube_path, analysis = extract_lut_from_reference(video_path, output_dir, strength)
    # Only advertise a LUT storage key once it has been uploaded to R2.  The
    # local cube_path is useless to downstream render workers, which need an
    # object-storage key they can download.
    lut_storage_key: Optional[str] = None

    if cube_path and project_id:
        try:
            async with httpx.AsyncClient() as client:
                create_resp = await client.post(
                    f"{settings.api_base}/internal/assets",
                    json={
                        "projectId": project_id,
                        "type": "lut",
                        "filename": "style.cube",
                        "mimeType": "application/vnd.adobe.cube",
                    },
                    headers=_internal_headers(),
                    timeout=30,
                )
                create_resp.raise_for_status()
                asset_data = create_resp.json()
                asset_id = asset_data["assetId"]
                asset_storage_key = asset_data["storageKey"]

                upload_file(cube_path, asset_storage_key, content_type="application/vnd.adobe.cube")

                size_bytes = os.path.getsize(cube_path)
                storage_url = get_presigned_download_url(asset_storage_key, expires_in=3600)

                await client.patch(
                    f"{settings.api_base}/internal/assets/{asset_id}/complete",
                    json={"sizeBytes": size_bytes, "storageUrl": storage_url},
                    headers=_internal_headers(),
                    timeout=30,
                )

                lut_storage_key = asset_storage_key
        except Exception as e:
            activity.logger.warning(f"Failed to upload LUT to R2: {e}")
            lut_storage_key = None

    return {
        "cube_path": cube_path,
        "color_palette": analysis.color_palette,
        "contrast_level": analysis.contrast_level,
        "saturation_level": analysis.saturation_level,
        "brightness_level": analysis.brightness_level,
        "lut_extracted": analysis.lut_extracted and lut_storage_key is not None,
        "lut_storage_key": lut_storage_key,
    }


@activity.defn
async def detect_text_overlays(video_path: str, fps_sample: float = 5.0) -> List[dict]:
    """Detect persistent text overlays in a video."""
    overlays = extract_text_overlays(video_path, fps_sample)
    return [o.model_dump() for o in overlays]


@activity.defn
async def analyze_motion(video_path: str, shot_boundaries: List[dict]) -> List[str]:
    """Classify camera motion for each shot boundary."""
    shots = [ShotBoundary(**s) for s in shot_boundaries]
    return analyze_camera_motion(video_path, shots)


@activity.defn
async def classify_shot_transitions(video_path: str, shot_boundaries: List[dict]) -> List[dict]:
    """Classify transition types for shot boundaries."""
    shots = [ShotBoundary(**s) for s in shot_boundaries]
    result = classify_transitions(video_path, shots)
    return [s.model_dump() for s in result]


@activity.defn
async def cleanup_style_assets(video_path: str, output_dir: str) -> None:
    """Remove the downloaded reference video and any scratch LUT directory."""
    try:
        if video_path and os.path.exists(video_path):
            os.remove(video_path)
    except OSError as e:
        activity.logger.warning(f"Failed to remove style video {video_path}: {e}")

    try:
        if output_dir and os.path.isdir(output_dir):
            shutil.rmtree(output_dir, ignore_errors=True)
    except OSError as e:
        activity.logger.warning(f"Failed to remove style output dir {output_dir}: {e}")
