# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
# Commercial SaaS use is prohibited without written permission.
"""SAM3 segmentation engine facade.

The real implementation lives in ``segment_worker.client.Sam3Segmenter``. This
module exposes the same functions the Temporal activity already calls, while
keeping the heavy SAM3 imports lazy and optional.
"""

from __future__ import annotations

import base64
import io
import logging
from typing import Any, Optional

from segment_worker.client import Sam3Segmenter

logger = logging.getLogger(__name__)

try:
    import cv2

    _CV2 = True
except Exception:  # pragma: no cover - optional dep
    _CV2 = False

try:
    from PIL import Image

    _PIL = True
except Exception:  # pragma: no cover - optional dep
    _PIL = False

try:
    import numpy as np

    _NUMPY = True
except Exception:  # pragma: no cover - optional dep
    _NUMPY = False

_segmenter: Optional[Sam3Segmenter] = None


def _get_segmenter() -> Sam3Segmenter:
    """Return the module-level SAM3 segmenter singleton."""
    global _segmenter
    if _segmenter is None:
        _segmenter = Sam3Segmenter()
    return _segmenter


def is_segmentation_available() -> bool:
    """Return True if SAM3 image inference can be attempted."""
    return _get_segmenter().available()


def detect_subject_mask_image(
    image_path: str,
    prompt: str,
    version: str = "sam3",
) -> dict[str, Any]:
    """Run open-vocabulary segmentation on a single image."""
    return _get_segmenter().segment_image(image_path, prompt)


def detect_subject_mask_video(
    video_path: str,
    prompt: str,
    frame_index: int = 0,
    version: str = "sam3.1",
) -> dict[str, Any]:
    """Run open-vocabulary segmentation + tracking on a video."""
    return _get_segmenter().segment_video(video_path, prompt, frame_index)


def _skip(reason: str) -> dict[str, Any]:
    """Return a skipped result dict consistent with the SAM3 client."""
    return {
        "available": False,
        "skipped": True,
        "skipped_reason": reason,
        "masks": [],
        "boxes": [],
        "scores": [],
    }


def generate_subject_mask_for_identity(
    video_path: str,
    output_path: str,
    prompt: str,
    frame_index: int = 0,
    version: str = "sam3.1",
) -> dict[str, Any]:
    """Generate a subject mask video for an identity using SAM3.

    Wraps ``detect_subject_mask_video`` and writes the returned base64 PNG masks
    to an MP4 video file at ``output_path``.  If SAM3 is unavailable or no masks
    are produced, returns a skipped dict without raising.
    """
    if not _PIL or not _NUMPY:
        return _skip("PIL/numpy not available for mask video writing")

    result = detect_subject_mask_video(video_path, prompt, frame_index=frame_index, version=version)
    if result.get("skipped") or not result.get("available"):
        return result

    masks_by_frame = result.get("masks_by_frame", {})
    if not masks_by_frame:
        return _skip("SAM3 produced no masks")

    if not _CV2:
        return _skip("cv2 not available to encode mask video")

    sorted_frames = sorted(masks_by_frame.keys())
    first_masks = masks_by_frame[sorted_frames[0]]
    if not first_masks:
        return _skip("First mask frame is empty")

    try:
        first_img = Image.open(io.BytesIO(base64.b64decode(first_masks[0]))).convert("L")
    except Exception as exc:
        return _skip(f"Failed to decode first mask: {exc}")

    width, height = first_img.size
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(output_path, fourcc, 30.0, (width, height), isColor=False)
    if not writer.isOpened():
        return _skip(f"Could not open VideoWriter for {output_path}")

    try:
        for frame_idx in sorted_frames:
            masks = masks_by_frame.get(frame_idx, [])
            if masks:
                try:
                    img = Image.open(io.BytesIO(base64.b64decode(masks[0]))).convert("L")
                    arr = np.array(img)
                except Exception as exc:
                    logger.warning("Failed to decode mask for frame %s: %s", frame_idx, exc)
                    arr = np.zeros((height, width), dtype=np.uint8)
            else:
                arr = np.zeros((height, width), dtype=np.uint8)
            writer.write(arr)
    finally:
        writer.release()

    return {
        "available": True,
        "skipped": False,
        "output_path": output_path,
        "masks": [],
        "boxes": result.get("boxes", []),
        "scores": result.get("scores", []),
    }
