# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
"""Zoom punch-in filter primitive using a time-varying crop window."""

from __future__ import annotations


def zoom_punch_filter(
    rel_start: float,
    rel_end: float,
    target_scale: float = 1.3,
    duration_ms: int = 300,
    center_x: float = 0.5,
    center_y: float = 0.5,
    fps: float = 30.0,
) -> str:
    """Return an FFmpeg crop filter that zooms from 1x to ``target_scale``.

    The crop window grows over ``duration_ms`` (capped to the effect window)
    while keeping ``center_x/center_y`` anchored.  Frame-based ramping avoids
    the fractional ``t`` precision issues that can make short effects jumpy.
    """
    dur = min(duration_ms / 1000.0, rel_end - rel_start)
    start_frame = int(rel_start * fps)
    end_frame = start_frame + max(1, int(dur * fps))
    ramp_expr = f"max(0\\,min(1\\,(n-{start_frame})/({end_frame}-{start_frame})))"
    return (
        f"crop='iw/(1+({target_scale}-1)*{ramp_expr})':"
        f"'ih/(1+({target_scale}-1)*{ramp_expr})':"
        f"(iw-ow)*{center_x}:(ih-oh)*{center_y}"
    )
