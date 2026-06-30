# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
# Commercial SaaS use is prohibited without written permission.
"""Structural-change editing tier requiring anchor frames and user approval."""

from __future__ import annotations

import logging
from typing import Dict, Optional, Union

logger = logging.getLogger(__name__)


def _extract_anchor_frames(clip_path: str) -> tuple[str, str]:
    """Placeholder: extract the first and last frames of ``clip_path``.

    TODO: Implement via FFmpeg or cv2. Returns ``(first_frame_path, last_frame_path)``.
    """
    raise NotImplementedError("Anchor-frame extraction for structural change is not implemented yet.")


def _request_user_approval(target_prompt: str, anchor_paths: tuple[str, str]) -> bool:
    """Placeholder gate: require explicit user approval before heavy generative edits.

    TODO: Integrate with the project approval queue / UI. Returns True when the
    user confirms they want to proceed with the structural edit.
    """
    raise NotImplementedError("User-approval gate for structural change is not implemented yet.")


async def apply_structural_change_tier(
    clip_path: str,
    mask_per_frame: Union[str, Dict[int, str]],
    target_prompt: str,
    *,
    output_path: Optional[str] = None,
) -> str:
    """Apply a heavy structural change inside the masked region.

    Args:
        clip_path: Path to the source video clip.
        mask_per_frame: Path to a mask video or dict of frame-index to mask image.
        target_prompt: Text prompt describing the desired structural change.
        output_path: Optional destination path (ignored in skeleton).

    Returns:
        ``clip_path`` unchanged. The skeleton extracts first/last anchors and
        checks a user-approval gate, leaving actual generation for a follow-up PR.
    """
    first_frame, last_frame = _extract_anchor_frames(clip_path)
    logger.info(
        "Structural change skeleton called for %s with prompt %r (anchors: %s, %s)",
        clip_path,
        target_prompt,
        first_frame,
        last_frame,
    )

    # Approval gate placeholder. In production this blocks on explicit consent.
    approved = _request_user_approval(target_prompt, (first_frame, last_frame))
    if not approved:
        raise RuntimeError("User did not approve structural change")

    # TODO: Generate key-frame edits with video diffusion (e.g. CogVideo/SVD)
    # and in-paint/interpolate between anchors using the per-frame masks.
    return clip_path
