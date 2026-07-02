# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
# Commercial SaaS use is prohibited without written permission.
"""Stabilization helpers for shaky clip footage."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Optional


def stabilization_filter(method: str = "deshake") -> str:
    """Return an FFmpeg video filter string for stabilization.

    ``deshake`` is available in all FFmpeg builds. ``vidstab`` is higher quality
    but requires FFmpeg compiled with libvidstab.
    """
    if method == "vidstab":
        return "vidstabdetect=stepsize=6:shakiness=8:accuracy=9:result=/tmp/transforms.trf[vid];[vid]vidstabtransform=input=/tmp/transforms.trf:zoom=0:smoothing=10"
    return "deshake=rx=64:ry=64:blocksize=8"


def stabilize_clip(
    input_path: str,
    output_path: str,
    method: str = "deshake",
    ffmpeg_path: str = "ffmpeg",
) -> Optional[str]:
    """Stabilize a video clip and write it to ``output_path``.

    Returns the output path on success, None on failure.
    """
    vf = stabilization_filter(method)
    cmd = [
        ffmpeg_path,
        "-y",
        "-i", input_path,
        "-vf", vf,
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "23",
        "-c:a", "copy",
        output_path,
    ]
    try:
        subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True, text=True)
        return output_path
    except Exception:
        return None


def stabilization_available(method: str = "deshake") -> bool:
    """Check whether the chosen stabilization method is available."""
    if method == "deshake":
        return shutil.which("ffmpeg") is not None
    if method == "vidstab":
        try:
            out = subprocess.check_output(["ffmpeg", "-filters"], stderr=subprocess.DEVNULL, text=True)
            return "vidstabdetect" in out and "vidstabtransform" in out
        except Exception:
            return False
    return False
