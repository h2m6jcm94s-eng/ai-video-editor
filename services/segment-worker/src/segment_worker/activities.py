# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
# Commercial SaaS use is prohibited without written permission.
"""Temporal activities for the segmentation worker."""

from __future__ import annotations

import os
import tempfile
from typing import Any

from temporalio import activity

from shared_py.storage import download_asset

from segment_worker.engine import detect_subject_mask_image, detect_subject_mask_video


@activity.defn
async def segment_subject(
    asset_id: str,
    storage_key: str,
    prompt: str,
    mode: str = "image",
    frame_index: int = 0,
) -> dict[str, Any]:
    """Download an asset and run SAM3 segmentation on it.

    Args:
        asset_id: UUID of the asset.
        storage_key: R2/S3 object key for the asset.
        prompt: Text prompt describing the subject to segment.
        mode: "image" or "video".
        frame_index: For video mode, the frame to prompt on.

    Returns:
        A serializable result dict from the engine.  If SAM3 is unavailable,
        the result has ``available=False`` and a ``skipped_reason``.
    """
    ext = os.path.splitext(storage_key)[1] or ".tmp"
    local_path = os.path.join(tempfile.gettempdir(), f"ave_segment_{asset_id}{ext}")
    download_asset(storage_key, local_path)

    if mode == "video":
        return detect_subject_mask_video(local_path, prompt, frame_index=frame_index)
    return detect_subject_mask_image(local_path, prompt)
