# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
# Commercial SaaS use is prohibited without written permission.
"""Color-shift editing tier applied through a per-frame mask."""

from __future__ import annotations

import os
import subprocess
import tempfile
from typing import Any, Dict, Optional, Union


def _run_ffmpeg(cmd: list[str], context: str) -> None:
    """Run FFmpeg with rich error context on failure."""
    try:
        subprocess.run(cmd, check=True, capture_output=True, stdin=subprocess.DEVNULL)
    except subprocess.CalledProcessError as e:
        stderr = e.stderr.decode("utf-8", errors="replace") if e.stderr else ""
        raise RuntimeError(
            f"FFmpeg failed during {context}: {e.returncode}\n"
            f"Command: {' '.join(cmd[:20])}...\n"
            f"Stderr: {stderr[:2000]}"
        ) from e


def _mask_video_from_per_frame(
    per_frame: Dict[int, str],
    reference_path: str,
    output_path: str,
) -> str:
    """Build a single mask video from a mapping of frame index to image path.

    TODO: Implement per-frame mask assembly when the SAM3 client returns
    discrete images rather than a mask video. For now this raises.
    """
    raise NotImplementedError(
        "Per-frame mask assembly is not implemented yet; pass a mask video path."
    )


def _build_color_filter_graph(color_spec: dict[str, Any]) -> str:
    """Translate a color spec into an FFmpeg filter graph segment.

    Args:
        color_spec: Dict with optional keys ``hue`` (degrees), ``saturation``
            (float multiplier), ``brightness`` (float offset), ``contrast``
            (float), and ``color_balance`` (rgb channel gains).

    Returns:
        Filter graph substring operating on the masked region.
    """
    filters: list[str] = []

    hue = color_spec.get("hue")
    saturation = color_spec.get("saturation")
    if hue is not None or saturation is not None:
        h = float(hue) if hue is not None else 0.0
        s = float(saturation) if saturation is not None else 1.0
        filters.append(f"hue=h={h}:s={s}")

    brightness = color_spec.get("brightness")
    contrast = color_spec.get("contrast")
    if brightness is not None or contrast is not None:
        # eq filter uses contrast and brightness offsets.
        b = float(brightness) if brightness is not None else 0.0
        c = float(contrast) if contrast is not None else 1.0
        filters.append(f"eq=contrast={c}:brightness={b}")

    color_balance = color_spec.get("color_balance")
    if color_balance:
        # colorbalance shadows/midtones/highlights in r/g/b.
        # Expects keys like rs, gm, bh etc. Pass-through for now.
        filters.append("colorbalance")

    if not filters:
        # Identity filter so the graph still has a node.
        filters.append("copy")

    return ",".join(filters)


def _apply_bounce_light_correction(
    output_path: str,
    mask_path: str,
    color_spec: dict[str, Any],
) -> None:
    """Placeholder for bounce-light / spill correction after color shift.

    TODO: Sample border pixels around the masked region and push the shifted
    color toward the surrounding ambient light so the edit does not look
    artificially cut out.
    """
    pass


def apply_color_shift_tier(
    clip_path: str,
    mask_per_frame: Union[str, Dict[int, str]],
    color_spec: dict[str, Any],
    *,
    output_path: Optional[str] = None,
) -> str:
    """Apply a color shift to ``clip_path`` masked by ``mask_per_frame``.

    Args:
        clip_path: Path to the source video clip.
        mask_per_frame: Either a path to a pre-rendered mask video, or a dict
            mapping frame index to per-frame mask image path.
        color_spec: Dict describing the desired color manipulation.
        output_path: Optional destination path. If omitted, a sibling file in
            the system temp directory is created.

    Returns:
        Path to the rendered output video.
    """
    if isinstance(mask_per_frame, dict):
        with tempfile.TemporaryDirectory(prefix="ave_color_shift_masks_") as td:
            mask_video = os.path.join(td, "mask.mp4")
            _mask_video_from_per_frame(mask_per_frame, clip_path, mask_video)
            return apply_color_shift_tier(clip_path, mask_video, color_spec, output_path=output_path)

    mask_path = str(mask_per_frame)

    if output_path is None:
        fd, output_path = tempfile.mkstemp(suffix=".mp4", prefix="ave_color_shift_")
        os.close(fd)

    color_filters = _build_color_filter_graph(color_spec)

    # Filter graph:
    # [0:v] color-shifted stream
    # [1:v] grayscale mask stream -> luminance key -> alpha
    # compose the shifted video over the original using the mask as alpha.
    filter_complex = (
        "[0:v]format=pix_fmts=yuva420p[base];"
        "[1:v]format=gray,alphaextract,fade=t=out:st=0:d=0[mask];"
        f"[base]{color_filters}[shifted];"
        "[shifted][mask]alphamerge[shifted_alpha];"
        "[0:v][shifted_alpha]overlay=0:0:format=auto[outv]"
    )

    cmd = [
        "ffmpeg", "-y",
        "-i", clip_path,
        "-i", mask_path,
        "-filter_complex", filter_complex,
        "-map", "[outv]",
        "-an",
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "18",
        "-pix_fmt", "yuv420p",
        output_path,
    ]

    _run_ffmpeg(cmd, "color shift tier")
    _apply_bounce_light_correction(output_path, mask_path, color_spec)
    return output_path
