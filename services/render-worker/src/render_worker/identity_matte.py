# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
# Commercial SaaS use is prohibited without written permission.
"""Identity-aware matting for the render pipeline.

This module clusters face detections across clips, picks project protagonists,
and requests SAM3 masks only for clips where a protagonist is actually present.
When SAM3 is unavailable it still produces identity presence metadata and simply
omits mask paths.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List

try:
    import cv2

    _CV2 = True
except Exception:  # pragma: no cover - optional dep
    _CV2 = False

try:
    import numpy as np
except Exception:  # pragma: no cover - optional dep
    np = None  # type: ignore[assignment]

from ingest_worker.identity import ensure_faces
from reason_worker.protagonist_pick import select_protagonists
from segment_worker.engine import generate_subject_mask_for_identity
from shared_py.identity_cluster import Identity
from shared_py.models import CutList
from shared_py.tuning import IDENTITY

logger = logging.getLogger(__name__)


def _clip_has_identity(clip_id: str, identity: Identity) -> bool:
    """Return True if the identity has any face detection in the given clip."""
    return any(d.clip_id == clip_id for d in identity.face_detections)


def build_identity_masks(
    cutlist: Any,
    clip_paths: Dict[str, str],
    temp_dir: str,
) -> tuple[Dict[str, str], Dict[int, List[int]]]:
    """Build identity-aware masks for the selected clips in a cutlist.

    Args:
        cutlist: A CutList object or a dict that can be parsed into one.
        clip_paths: Mapping from clip_id to local file path.
        temp_dir: Directory where generated mask videos are written.

    Returns:
        ``(mask_paths, slot_identity_info)`` where ``mask_paths`` maps clip_id to
        a generated mask video path (only for clips with a protagonist present
        and SAM3 available), and ``slot_identity_info`` maps slot index to the
        list of protagonist identity ids detected in that slot's clip.

    Important: this function only *reads* the selected clips in ``cutlist`` and
    decides whether to generate a mask for each. It never removes clips from the
    candidate pool or from the cutlist; non-protagonist clips simply receive no
    mask path and an empty ``identity_ids_present`` list.
    """
    cutlist_obj = cutlist if isinstance(cutlist, CutList) else CutList(**cutlist)

    # Ensure face caches exist for every selected clip.
    for slot in cutlist_obj.slots:
        clip_id = slot.selected_clip_id
        if not clip_id or clip_id not in clip_paths:
            continue
        try:
            ensure_faces(clip_paths[clip_id], clip_id, sample_fps=DEFAULT_SAMPLE_FPS)
        except Exception as exc:
            logger.warning("Failed to ensure faces for clip %s: %s", clip_id, exc)

    protagonists, protagonist_ids = select_protagonists(
        clip_paths,
        sample_fps=IDENTITY.SAMPLE_FPS,
        top_n=IDENTITY.TOP_N,
    )

    slot_identity_info: Dict[int, List[int]] = {}
    for slot in cutlist_obj.slots:
        clip_id = slot.selected_clip_id
        if not clip_id or clip_id not in clip_paths:
            slot_identity_info[slot.index] = []
            continue
        present_ids = [p.id for p in protagonists if _clip_has_identity(clip_id, p)]
        slot_identity_info[slot.index] = present_ids

    mask_paths: Dict[str, str] = {}
    processed_clips: set[str] = set()
    for slot in cutlist_obj.slots:
        clip_id = slot.selected_clip_id
        if not clip_id or clip_id in processed_clips or clip_id not in clip_paths:
            continue
        processed_clips.add(clip_id)

        present_ids = slot_identity_info.get(slot.index, [])
        if not present_ids:
            continue

        output_path = os.path.join(temp_dir, f"identity_mask_{clip_id}.mp4")
        try:
            result = generate_subject_mask_for_identity(
                video_path=clip_paths[clip_id],
                output_path=output_path,
                prompt="the protagonist",
                frame_index=0,
                version="sam3.1",
            )
            if result.get("skipped"):
                logger.info(
                    "SAM3 skipped identity mask for clip %s: %s",
                    clip_id,
                    result.get("skipped_reason"),
                )
                continue
            mask_paths[clip_id] = output_path
        except Exception as exc:
            logger.warning("Failed to generate identity mask for clip %s: %s", clip_id, exc)

    return mask_paths, slot_identity_info


def blank_mask_video(output_path: str, width: int, height: int, fps: float, duration_s: float) -> str:
    """Generate an all-black MP4 mask video.

    This helper is reserved for future PR #2 use and is intentionally kept
    available even though PR #1 does not consume it.
    """
    if not _CV2:
        raise RuntimeError("cv2 not available; cannot generate blank mask video")
    if np is None:
        raise RuntimeError("numpy not available; cannot generate blank mask video")

    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(output_path, fourcc, fps, (width, height), isColor=False)
    if not writer.isOpened():
        raise RuntimeError(f"Could not open VideoWriter for {output_path}")

    total_frames = max(1, int(fps * duration_s))
    black_frame = np.zeros((height, width), dtype=np.uint8)
    try:
        for _ in range(total_frames):
            writer.write(black_frame)
    finally:
        writer.release()

    return output_path
