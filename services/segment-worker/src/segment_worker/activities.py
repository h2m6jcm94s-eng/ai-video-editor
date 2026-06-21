# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
# Commercial SaaS use is prohibited without written permission.
"""Temporal activities for the segmentation worker."""

from __future__ import annotations

import base64
import binascii
import os
import tempfile
from typing import Any

import httpx
from temporalio import activity

from shared_py.config import settings
from shared_py.storage import download_asset, upload_file

from segment_worker.engine import detect_subject_mask_image, detect_subject_mask_video


def _internal_headers() -> dict[str, str]:
    token = os.environ.get("INTERNAL_WORKER_TOKEN")
    if not token:
        raise RuntimeError("INTERNAL_WORKER_TOKEN not set")
    return {"x-internal-token": token}


def _create_mask_asset(project_id: str, source_asset_id: str, index: int) -> dict[str, str]:
    """Create a first-class mask asset row via the internal API."""
    filename = f"mask-{index}.png"
    resp = httpx.post(
        f"{settings.api_base}/internal/assets",
        json={
            "projectId": project_id,
            "type": "mask",
            "filename": filename,
            "mimeType": "image/png",
        },
        headers=_internal_headers(),
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    return {
        "assetId": data["assetId"],
        "storageKey": data["storageKey"],
    }


def _complete_mask_asset(
    asset_id: str, storage_key: str, png_bytes: bytes, metadata: dict[str, Any]
) -> None:
    """Upload the mask PNG and mark the asset row complete."""
    ext = ".png"
    local_path = os.path.join(tempfile.gettempdir(), f"ave_mask_{asset_id}{ext}")
    with open(local_path, "wb") as f:
        f.write(png_bytes)
    try:
        upload_file(local_path, storage_key, content_type="image/png")
    finally:
        try:
            os.remove(local_path)
        except OSError:
            pass

    resp = httpx.patch(
        f"{settings.api_base}/internal/assets/{asset_id}/complete",
        json={
            "sizeBytes": len(png_bytes),
            "metadata": metadata,
        },
        headers=_internal_headers(),
        timeout=30,
    )
    resp.raise_for_status()


def _patch_source_segment_metadata(
    source_asset_id: str,
    prompt: str,
    mask_asset_ids: list[str],
    boxes: list[list[float]] | None,
    scores: list[float] | None,
) -> None:
    """Merge segmentation summary into the source asset's metadata."""
    payload: dict[str, Any] = {
        "metadata": {
            "segmentation": {
                "prompt": prompt,
                "maskAssetIds": mask_asset_ids,
                "maskCount": len(mask_asset_ids),
            }
        }
    }
    if boxes:
        payload["metadata"]["segmentation"]["boxes"] = boxes
    if scores:
        payload["metadata"]["segmentation"]["scores"] = scores

    resp = httpx.patch(
        f"{settings.api_base}/internal/assets/{source_asset_id}/metadata",
        json=payload,
        headers=_internal_headers(),
        timeout=30,
    )
    resp.raise_for_status()


# Guardrails for worker-supplied mask payloads.
_MAX_MASK_COUNT = 100
_MAX_MASK_B64_BYTES = 50 * 1024 * 1024
_MAX_TOTAL_MASK_BYTES = 200 * 1024 * 1024


def _persist_masks_as_assets(
    project_id: str,
    source_asset_id: str,
    prompt: str,
    b64_masks: list[str],
    boxes: list[list[float]] | None,
    scores: list[float] | None,
) -> list[str]:
    """Create asset rows for each mask, upload PNGs, complete them, and link back."""
    # Guard against abuse / malformed worker payloads.
    if len(b64_masks) > _MAX_MASK_COUNT:
        raise ValueError(f"Too many masks: {len(b64_masks)}")

    decoded_masks: list[bytes] = []
    total_bytes = 0
    for b64 in b64_masks:
        if len(b64) > _MAX_MASK_B64_BYTES:
            raise ValueError("Individual mask payload exceeds size limit")
        try:
            png_bytes = base64.b64decode(b64)
        except binascii.Error as exc:
            raise ValueError(f"Invalid base64 mask data: {exc}") from exc
        total_bytes += len(png_bytes)
        if total_bytes > _MAX_TOTAL_MASK_BYTES:
            raise ValueError("Total mask payload exceeds size limit")
        decoded_masks.append(png_bytes)

    mask_asset_ids: list[str] = []
    for idx, png_bytes in enumerate(decoded_masks):
        info = _create_mask_asset(project_id, source_asset_id, idx)
        _complete_mask_asset(
            info["assetId"],
            info["storageKey"],
            png_bytes,
            metadata={
                "sourceAssetId": source_asset_id,
                "prompt": prompt,
                "maskIndex": idx,
            },
        )
        mask_asset_ids.append(info["assetId"])

    _patch_source_segment_metadata(
        source_asset_id, prompt, mask_asset_ids, boxes, scores
    )
    return mask_asset_ids


@activity.defn
async def segment_subject(
    asset_id: str,
    storage_key: str,
    prompt: str,
    mode: str = "image",
    frame_index: int = 0,
    project_id: str = "",
) -> dict[str, Any]:
    """Download an asset and run SAM3 segmentation on it.

    Args:
        asset_id: UUID of the asset.
        storage_key: R2/S3 object key for the asset.
        prompt: Text prompt describing the subject to segment.
        mode: "image" or "video".
        frame_index: For video mode, the frame to prompt on.
        project_id: UUID of the owning project (used for mask asset creation).

    Returns:
        A serializable result dict from the engine.  If SAM3 is unavailable,
        the result has ``available=False`` and a ``skipped_reason``.
    """
    ext = os.path.splitext(storage_key)[1] or ".tmp"
    local_path = os.path.join(tempfile.gettempdir(), f"ave_segment_{asset_id}{ext}")
    download_asset(storage_key, local_path)

    try:
        if mode == "video":
            result = detect_subject_mask_video(
                local_path, prompt, frame_index=frame_index
            )
        else:
            result = detect_subject_mask_image(local_path, prompt)
    finally:
        try:
            os.remove(local_path)
        except OSError:
            pass

    # Persist generated masks as first-class assets and link them to the source
    # asset metadata so the render pipeline can locate them later.
    masks_b64 = result.get("masks") or []
    if not masks_b64 and result.get("masks_by_frame"):
        masks_b64 = [
            m for masks in result["masks_by_frame"].values() for m in masks
        ]
    if project_id and result.get("available") and masks_b64:
        try:
            mask_asset_ids = _persist_masks_as_assets(
                project_id,
                asset_id,
                prompt,
                masks_b64,
                result.get("boxes"),
                result.get("scores"),
            )
            result["mask_asset_ids"] = mask_asset_ids
        except Exception as e:
            activity.logger.warning(
                f"Failed to persist segmentation masks for {asset_id}: {e}"
            )
            result["mask_persist_error"] = str(e)

    return result
