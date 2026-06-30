# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
# Commercial SaaS use is prohibited without written permission.
"""Temporal activities for the render worker."""

import os
import tempfile
from typing import Dict, List, Optional

import httpx
from temporalio import activity

from render_worker.compiler import compile_timeline, resolve_render_dimensions, _has_nvenc
from render_worker.identity_matte import build_identity_masks
from shared_py.config import settings
from shared_py.models import CutList, RenderConfig
from shared_py.storage import download_asset, get_presigned_download_url, upload_file


def _internal_headers() -> Dict[str, str]:
    token = os.environ.get("INTERNAL_WORKER_TOKEN")
    if not token:
        raise RuntimeError("INTERNAL_WORKER_TOKEN not set")
    return {"x-internal-token": token}


async def _resolve_mask_storage_key(mask_asset_id: str) -> Optional[str]:
    """Fetch the R2 storage key for a mask asset via the internal API."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{settings.api_base}/internal/assets/{mask_asset_id}",
            headers=_internal_headers(),
            timeout=30,
        )
    resp.raise_for_status()
    data = resp.json()
    asset = data.get("asset") or data
    return asset.get("storageKey")


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
    style_analysis: Optional[dict] = None,
    mask_source_map: Optional[Dict[str, str]] = None,
    export_preset: Optional[str] = None,
    style_tier: str = "full_remix",
    duration_sec: Optional[float] = None,
) -> str:
    """Compile the cut-list into a final MP4."""
    cutlist_obj = CutList(**cutlist)

    # Apply an explicit duration cap from render options. This lets users request
    # a shorter output than the generated cutlist without regenerating.
    if duration_sec is not None and duration_sec > 0:
        current = cutlist_obj.globals.total_duration_s
        if current is None or duration_sec < current:
            cutlist_obj.globals.total_duration_s = duration_sec
            for track in cutlist_obj.audio_tracks:
                track.end_s = min(track.end_s, duration_sec)

    # Map slots to local clip paths
    clip_paths: Dict[str, str] = {}
    for slot in cutlist_obj.slots:
        clip_id = slot.selected_clip_id
        if clip_id and clip_id in local_paths:
            clip_paths[clip_id] = local_paths[clip_id]

    # Build identity-aware masks.  When SAM3 is unavailable this still populates
    # slot.identity_ids_present and simply omits mask paths.
    identity_mask_paths: Dict[str, str] = {}
    try:
        identity_mask_paths, slot_identity_info = build_identity_masks(
            cutlist_obj, clip_paths, tempfile.gettempdir()
        )
        for slot in cutlist_obj.slots:
            slot.identity_ids_present = slot_identity_info.get(slot.index, [])
    except Exception as e:
        activity.logger.warning(f"Identity-aware matting failed, continuing without masks: {e}")
        identity_mask_paths = {}

    # Resolve song path if available
    song_path = local_paths.get(song_asset_id) if song_asset_id else None

    # Resolve explicit audio tracks (independent of the legacy song path).
    audio_paths: Dict[str, str] = {}
    for track in cutlist_obj.audio_tracks:
        path = local_paths.get(track.asset_id)
        if path:
            audio_paths[track.asset_id] = path

    # Download LUT if the project style analysis references one stored in R2.
    lut_path: Optional[str] = None
    if style_analysis:
        lut_storage_key = style_analysis.get("lut_storage_key")
        if lut_storage_key:
            ext = os.path.splitext(lut_storage_key)[1] or ".cube"
            lut_path = os.path.join(
                tempfile.gettempdir(),
                f"ave_lut_{_activity_run_id()}{ext}",
            )
            try:
                lut_path = download_asset(lut_storage_key, lut_path)
            except Exception as e:
                activity.logger.warning(f"Failed to download LUT {lut_storage_key}: {e}")
                lut_path = None

    # Download segmentation masks. We support two resolution strategies:
    # 1. Per-slot masks: a slot can reference a specific mask asset id; these
    #    take precedence and are keyed by slot index.
    # 2. Per-clip masks: the legacy path uses the first mask found on a source
    #    asset and applies it to every slot that uses that clip.
    mask_paths: Dict[str, str] = {}
    slot_mask_paths: Dict[int, str] = {}
    mask_source_map = mask_source_map or {}

    # Collect per-slot mask asset ids from the cut-list.
    slot_mask_asset_ids: Dict[int, str] = {}
    for slot in cutlist_obj.slots:
        if slot.mask_asset_id:
            slot_mask_asset_ids[slot.index] = slot.mask_asset_id

    # Resolve storage keys for per-slot masks. mask_source_map may already
    # contain asset_id -> storage_key entries added by the API; if not, we try
    # to download the asset by its id using the internal storage layer.
    for slot_index, mask_asset_id in slot_mask_asset_ids.items():
        mask_storage_key = mask_source_map.get(mask_asset_id)
        if not mask_storage_key:
            try:
                mask_storage_key = await _resolve_mask_storage_key(mask_asset_id)
            except Exception as e:
                activity.logger.warning(f"Could not resolve storage key for mask {mask_asset_id}: {e}")
                continue
        if not mask_storage_key:
            continue
        try:
            mask_path = os.path.join(
                tempfile.gettempdir(),
                f"ave_mask_slot_{slot_index}_{mask_asset_id}_{_activity_run_id()}.png",
            )
            slot_mask_paths[slot_index] = download_asset(mask_storage_key, mask_path)
        except Exception as e:
            activity.logger.warning(f"Failed to download mask {mask_storage_key} for slot {slot_index}: {e}")

    # Merge identity-aware masks. These take precedence over legacy masks
    # because they were generated specifically for this render.
    mask_paths.update(identity_mask_paths)

    # Legacy per-clip masks (keyed by clip_id).
    for clip_id, mask_storage_key in mask_source_map.items():
        # Skip entries that are actually slot mask asset ids, not clip ids.
        if clip_id in slot_mask_asset_ids.values():
            continue
        if clip_id not in local_paths or not mask_storage_key:
            continue
        try:
            mask_path = os.path.join(
                tempfile.gettempdir(),
                f"ave_mask_{clip_id}_{_activity_run_id()}.png",
            )
            mask_paths[clip_id] = download_asset(mask_storage_key, mask_path)
        except Exception as e:
            activity.logger.warning(f"Failed to download mask {mask_storage_key} for clip {clip_id}: {e}")

    # Resolve output dimensions from export preset or cut-list aspect ratio.
    width, height = resolve_render_dimensions(
        export_preset,
        cutlist_obj.globals.aspect_ratio,
    )

    output_path = os.path.join(
        tempfile.gettempdir(),
        f"ave_render_{width}x{height}_{cutlist_obj.globals.total_duration_s:.0f}s_{_activity_run_id()}.mp4",
    )

    # Auto-enable NVENC when the worker has a capable NVIDIA GPU.  Operators can
    # opt out by setting AVE_DISABLE_NVENC=1.  CUDA decode is opt-in via
    # AVE_USE_HWACCEL=1 because some source files/filters still need software decode.
    use_nvenc = _has_nvenc() and not os.environ.get("AVE_DISABLE_NVENC")
    use_hwaccel = os.environ.get("AVE_USE_HWACCEL", "0") == "1"

    config = RenderConfig(
        output_path=output_path,
        width=width,
        height=height,
        fps=30,
        video_codec="h264_nvenc" if use_nvenc else "libx264",
        video_preset="slow",
        video_crf=23,
        audio_codec="aac",
        audio_bitrate="192k",
        pix_fmt="yuv420p",
        song_path=song_path,
        audio_tracks=cutlist_obj.audio_tracks,
        audio_paths=audio_paths,
        lut_path=lut_path,
        mask_paths=mask_paths,
        slot_mask_paths=slot_mask_paths,
        use_nvenc=use_nvenc,
        use_hwaccel=use_hwaccel,
    )

    compile_timeline(cutlist_obj, clip_paths, output_path, config, style_tier=style_tier)
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
async def record_render_outcome_activity(render_id: str, outcome_patch: dict) -> dict:
    """Record an implicit outcome event (exported, downloaded, abandoned, etc.)."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{settings.api_base}/renders/{render_id}/outcomes",
            json=outcome_patch,
            headers=_internal_headers(),
            timeout=30,
        )
    resp.raise_for_status()
    return {"ok": True}


@activity.defn
async def ingest_render_to_corpus(render_id: str, quality_weight: float = 0.5) -> dict:
    """Trigger corpus ingestion for a completed render."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{settings.api_base}/internal/renders/{render_id}/ingest-to-corpus",
            json={"qualityWeight": quality_weight},
            headers=_internal_headers(),
            timeout=30,
        )
    resp.raise_for_status()
    return resp.json()


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
