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
from style_worker.genome.extract import extract_genome
from style_worker.lut_extract import extract_lut_from_reference
from style_worker.reference_analysis import ReferenceAnalysis, analyze_reference
from style_worker.text_extract import extract_text_overlays
from style_worker.transition_type import classify_transitions
from shared_py.config import settings
from shared_py.models import BeatGrid, ShotBoundary, StyleAnalysis
from shared_py.storage import download_asset, get_presigned_download_url


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
    reference_analysis: Optional[dict] = None,
) -> dict:
    """Extract a .cube LUT from a reference video and persist it to R2."""
    if reference_analysis:
        cached = ReferenceAnalysis.from_cache_dict(reference_analysis)
        if cached.lut_storage_key:
            return {
                "cube_path": cached.lut_path,
                "color_palette": cached.style_analysis.color_palette,
                "contrast_level": cached.style_analysis.contrast_level,
                "saturation_level": cached.style_analysis.saturation_level,
                "brightness_level": cached.style_analysis.brightness_level,
                "lut_extracted": True,
                "lut_storage_key": cached.lut_storage_key,
            }

    if not output_dir:
        output_dir = tempfile.mkdtemp(prefix="ave_style_")

    asset_id = reference_analysis.get("assetId") if reference_analysis else None
    cube_path, analysis = extract_lut_from_reference(
        video_path, output_dir, strength, asset_id=asset_id
    )
    # The cube is persisted to storage by ``extract_lut_from_reference`` when an
    # asset_id is provided. We only need to register the asset row and mark it
    # complete; the bytes are already in the configured backend.
    lut_storage_key: Optional[str] = analysis.lut_storage_key

    if cube_path and project_id and lut_storage_key:
        try:
            async with httpx.AsyncClient() as client:
                create_resp = await client.post(
                    f"{settings.api_base}/internal/assets",
                    json={
                        "projectId": project_id,
                        "type": "lut",
                        "filename": "style.cube",
                        "mimeType": "application/vnd.adobe.cube",
                        "storageKey": lut_storage_key,
                    },
                    headers=_internal_headers(),
                    timeout=30,
                )
                create_resp.raise_for_status()
                asset_data = create_resp.json()
                created_asset_id = asset_data["assetId"]

                size_bytes = os.path.getsize(cube_path)
                storage_url = get_presigned_download_url(lut_storage_key, expires_in=3600)

                await client.patch(
                    f"{settings.api_base}/internal/assets/{created_asset_id}/complete",
                    json={"sizeBytes": size_bytes, "storageUrl": storage_url},
                    headers=_internal_headers(),
                    timeout=30,
                )
        except Exception as e:
            activity.logger.warning(f"Failed to register LUT asset: {e}")
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
async def extract_genome_activity(
    video_path: str,
    beat_grid: Optional[List[dict]] = None,
    shot_boundaries: Optional[List[dict]] = None,
    style_analysis: Optional[dict] = None,
    project_clips: Optional[Dict[str, dict]] = None,
    reference_analysis: Optional[dict] = None,
) -> dict:
    """Extract a 50-feature Style Genome fingerprint from a reference video."""
    if reference_analysis:
        cached = ReferenceAnalysis.from_cache_dict(reference_analysis)
        return cached.style_genome.model_dump(by_alias=True)

    bg = BeatGrid(**beat_grid) if beat_grid else None
    sb = [ShotBoundary(**s) for s in shot_boundaries] if shot_boundaries else None
    sa = StyleAnalysis(**style_analysis) if style_analysis else None
    return extract_genome(video_path, bg, sb, sa, project_clips)


@activity.defn
async def analyze_reference_activity(
    asset_id: str,
    storage_key: str,
    project_id: str = "",
    lut_strength: float = 0.5,
    beat_grid: Optional[dict] = None,
    project_clips: Optional[Dict[str, dict]] = None,
    asset_metadata: Optional[dict] = None,
) -> dict:
    """Download a reference, analyze it once, upload the LUT, and cache the result.

    Returns a serialized ``ReferenceAnalysis`` dict that downstream activities
    can consume to avoid re-analyzing the same reference.
    """
    video_path = await download_reference_video(asset_id, storage_key)
    output_dir = tempfile.mkdtemp(prefix="ave_ref_")

    bg = BeatGrid(**beat_grid) if beat_grid else None
    ref = analyze_reference(
        video_path,
        asset_id=asset_id,
        asset_metadata=asset_metadata,
        output_dir=output_dir,
        lut_strength=lut_strength,
        beat_grid=bg,
        project_clips=project_clips,
    )

    # Register the LUT asset if one was produced and a project is associated.
    # The bytes were already persisted to storage by ``analyze_reference``.
    if ref.lut_path and project_id and ref.lut_storage_key:
        try:
            async with httpx.AsyncClient() as client:
                create_resp = await client.post(
                    f"{settings.api_base}/internal/assets",
                    json={
                        "projectId": project_id,
                        "type": "lut",
                        "filename": "style.cube",
                        "mimeType": "application/vnd.adobe.cube",
                        "storageKey": ref.lut_storage_key,
                    },
                    headers=_internal_headers(),
                    timeout=30,
                )
                create_resp.raise_for_status()
                asset_data = create_resp.json()
                lut_asset_id = asset_data["assetId"]

                size_bytes = os.path.getsize(ref.lut_path)
                storage_url = get_presigned_download_url(ref.lut_storage_key, expires_in=3600)

                await client.patch(
                    f"{settings.api_base}/internal/assets/{lut_asset_id}/complete",
                    json={"sizeBytes": size_bytes, "storageUrl": storage_url},
                    headers=_internal_headers(),
                    timeout=30,
                )
        except Exception as e:
            activity.logger.warning(f"Failed to register LUT asset: {e}")

    # Persist the analysis back to the reference asset metadata.
    try:
        async with httpx.AsyncClient() as client:
            await client.patch(
                f"{settings.api_base}/internal/assets/{asset_id}/metadata",
                json={"referenceAnalysis": ref.model_dump()},
                headers=_internal_headers(),
                timeout=30,
            )
    except Exception as e:
        activity.logger.warning(f"Failed to cache reference analysis: {e}")

    return {
        "referenceAnalysis": ref.model_dump(),
        "videoPath": video_path,
    }


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
