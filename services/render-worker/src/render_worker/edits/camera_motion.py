# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
# Commercial SaaS use is prohibited without written permission.
"""Keyframe-driven camera motion filters (pan / tilt / zoom).

Uses FFmpeg's ``zoompan`` filter with time-based expressions.  Applied to a
slot stream that is already trimmed to the slot duration, so ``t`` starts at
zero at slot in-point and ends at slot out-point.
"""

from typing import List, Optional, Tuple

from shared_py.models import Keyframe
from render_worker.keyframes import ffmpeg_expression, normalize_track


def _preset_keyframes(
    motion: str, intensity: float, duration_s: float
) -> Tuple[List[Keyframe], List[Keyframe], List[Keyframe]]:
    """Return (z_keyframes, x_norm_keyframes, y_norm_keyframes) for a named move."""
    t_end = max(0.1, duration_s)
    intensity = max(0.0, min(1.0, intensity))
    zoom_amp = 1.0 + intensity * 0.5
    pan_zoom = 1.0 + intensity * 0.3
    pan_reach = intensity * 0.6

    z = [Keyframe(t_s=0.0, value=1.0), Keyframe(t_s=t_end, value=1.0)]
    x = [Keyframe(t_s=0.0, value=0.0), Keyframe(t_s=t_end, value=0.0)]
    y = [Keyframe(t_s=0.0, value=0.0), Keyframe(t_s=t_end, value=0.0)]

    if motion == "zoom_in":
        z = [Keyframe(t_s=0.0, value=1.0), Keyframe(t_s=t_end, value=zoom_amp)]
    elif motion == "zoom_out":
        z = [Keyframe(t_s=0.0, value=zoom_amp), Keyframe(t_s=t_end, value=1.0)]
    elif motion == "push_in":
        z = [Keyframe(t_s=0.0, value=1.0), Keyframe(t_s=t_end, value=zoom_amp)]
    elif motion == "pull_out":
        z = [Keyframe(t_s=0.0, value=zoom_amp), Keyframe(t_s=t_end, value=1.0)]
    elif motion == "pan_left":
        z = [Keyframe(t_s=0.0, value=pan_zoom), Keyframe(t_s=t_end, value=pan_zoom)]
        x = [Keyframe(t_s=0.0, value=0.0), Keyframe(t_s=t_end, value=pan_reach)]
    elif motion == "pan_right":
        z = [Keyframe(t_s=0.0, value=pan_zoom), Keyframe(t_s=t_end, value=pan_zoom)]
        x = [Keyframe(t_s=0.0, value=pan_reach), Keyframe(t_s=t_end, value=0.0)]
    elif motion == "tilt_up":
        z = [Keyframe(t_s=0.0, value=pan_zoom), Keyframe(t_s=t_end, value=pan_zoom)]
        y = [Keyframe(t_s=0.0, value=0.0), Keyframe(t_s=t_end, value=pan_reach)]
    elif motion == "tilt_down":
        z = [Keyframe(t_s=0.0, value=pan_zoom), Keyframe(t_s=t_end, value=pan_zoom)]
        y = [Keyframe(t_s=0.0, value=pan_reach), Keyframe(t_s=t_end, value=0.0)]

    return z, x, y


def camera_motion_filter(
    width: int,
    height: int,
    motion: str,
    intensity: float = 0.3,
    duration_s: float = 1.0,
    keyframes: Optional[List[Keyframe]] = None,
) -> str:
    """Return a ``zoompan`` filter string for the camera move.

    The caller should apply this filter to a stream trimmed to exactly the
    desired slot duration so that ``t=0`` is the slot in-point.
    """
    if keyframes and len(keyframes) >= 2:
        z_kf = keyframes
        x_kf = [Keyframe(t_s=k.t_s, value=0.0) for k in keyframes]
        y_kf = [Keyframe(t_s=k.t_s, value=0.0) for k in keyframes]
    else:
        z_kf, x_kf, y_kf = _preset_keyframes(motion, intensity, duration_s)

    z_kf = normalize_track(z_kf, duration_s)
    x_kf = normalize_track(x_kf, duration_s)
    y_kf = normalize_track(y_kf, duration_s)

    z_expr = ffmpeg_expression(z_kf)
    x_norm_expr = ffmpeg_expression(x_kf)
    y_norm_expr = ffmpeg_expression(y_kf)

    # Convert normalized pan to pixel offset.  0 = centered, 1 = edge.
    x_expr = f"{x_norm_expr}*(iw-iw/{z_expr})"
    y_expr = f"{y_norm_expr}*(ih-ih/{z_expr})"

    return (
        f"zoompan=z='{z_expr}':x='{x_expr}':y='{y_expr}':s={width}x{height}:d=1"
    )
