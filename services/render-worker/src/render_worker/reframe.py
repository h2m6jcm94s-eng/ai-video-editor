# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
# Commercial SaaS use is prohibited without written permission.
"""Auto-reframe helpers for converting between aspect ratios."""

from __future__ import annotations

import subprocess
from typing import Optional, Tuple


def _probe_video_size(video_path: str) -> Tuple[int, int]:
    """Return (width, height) using ffprobe."""
    try:
        out = subprocess.check_output(
            [
                "ffprobe",
                "-v", "error",
                "-select_streams", "v:0",
                "-show_entries", "stream=width,height",
                "-of", "csv=s=x:p=0",
                video_path,
            ],
            stderr=subprocess.DEVNULL,
            text=True,
        )
        parts = out.strip().split("x")
        return int(parts[0]), int(parts[1])
    except Exception:
        return 1920, 1080


def parse_aspect_ratio(aspect: str) -> float:
    """Parse '9:16', '16:9', '1:1' etc into a width/height float."""
    aspect = aspect.replace("/", ":")
    if ":" in aspect:
        w, h = aspect.split(":", 1)
        return float(w) / max(float(h), 1.0)
    return float(aspect)


def compute_reframe_crop(
    input_width: int,
    input_height: int,
    target_aspect: str,
    subject_box: Optional[Tuple[float, float, float, float]] = None,
) -> Tuple[int, int, int, int]:
    """Return a crop rectangle (x, y, w, h) that matches the target aspect.

    ``subject_box`` is optional normalized (x, y, w, h) of the main subject;
    the crop is centered on it when possible.
    """
    target_whr = parse_aspect_ratio(target_aspect)
    input_whr = input_width / max(input_height, 1)

    if input_whr > target_whr:
        # Input is too wide; crop horizontally.
        crop_h = input_height
        crop_w = int(round(crop_h * target_whr))
    else:
        # Input is too tall; crop vertically.
        crop_w = input_width
        crop_h = int(round(crop_w / target_whr))

    crop_w = min(crop_w, input_width)
    crop_h = min(crop_h, input_height)

    if subject_box is not None:
        sx, sy, sw, sh = subject_box
        subject_cx = int((sx + sw / 2) * input_width)
        subject_cy = int((sy + sh / 2) * input_height)
        x = min(max(0, subject_cx - crop_w // 2), input_width - crop_w)
        y = min(max(0, subject_cy - crop_h // 2), input_height - crop_h)
    else:
        x = (input_width - crop_w) // 2
        y = (input_height - crop_h) // 2

    return x, y, crop_w, crop_h


def reframe_filter(
    video_path: str,
    target_aspect: str,
    subject_box: Optional[Tuple[float, float, float, float]] = None,
) -> str:
    """Return an FFmpeg crop filter string for reframing ``video_path``."""
    width, height = _probe_video_size(video_path)
    x, y, w, h = compute_reframe_crop(width, height, target_aspect, subject_box)
    return f"crop={w}:{h}:{x}:{y}"
