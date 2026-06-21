# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
# Commercial SaaS use is prohibited without written permission.
"""SAM3 segmentation engine facade.

The real implementation lives in ``segment_worker.client.Sam3Segmenter``. This
module exposes the same functions the Temporal activity already calls, while
keeping the heavy SAM3 imports lazy and optional.
"""

from __future__ import annotations

from typing import Any, Optional

from segment_worker.client import Sam3Segmenter

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
