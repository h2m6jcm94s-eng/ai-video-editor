# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
# Commercial SaaS use is prohibited without written permission.
"""Generic keyframe interpolation helpers used by effects and layer compositing."""

from typing import List, Sequence

from shared_py.models import Keyframe


def lerp(t: float, t0: float, t1: float, v0: float, v1: float) -> float:
    """Linear interpolation between two keyframe values."""
    if t1 == t0:
        return float(v0)
    ratio = max(0.0, min(1.0, (t - t0) / (t1 - t0)))
    return float(v0) + ratio * (float(v1) - float(v0))


def sample(keyframes: Sequence[Keyframe], t: float) -> float:
    """Sample a scalar keyframe track at time ``t``."""
    if not keyframes:
        return 0.0
    kfs = sorted(keyframes, key=lambda k: k.t_s)
    if t <= kfs[0].t_s:
        return float(kfs[0].value)
    if t >= kfs[-1].t_s:
        return float(kfs[-1].value)
    for i in range(len(kfs) - 1):
        k0, k1 = kfs[i], kfs[i + 1]
        if k0.t_s <= t <= k1.t_s:
            return lerp(t, k0.t_s, k1.t_s, float(k0.value), float(k1.value))
    return float(kfs[-1].value)


def ffmpeg_expression(keyframes: Sequence[Keyframe]) -> str:
    """Build an FFmpeg expression string that linearly interpolates keyframes over t.

    The expression uses nested ``if(t<t1, ...)`` guards so it can be dropped
    directly into FFmpeg filter options that evaluate ``t`` in seconds.
    """
    if not keyframes:
        return "0"
    kfs = sorted(keyframes, key=lambda k: k.t_s)
    if len(kfs) == 1:
        return str(float(kfs[0].value))
    segments = []
    for i in range(len(kfs) - 1):
        t0 = float(kfs[i].t_s)
        t1 = float(kfs[i + 1].t_s)
        v0 = float(kfs[i].value)
        v1 = float(kfs[i + 1].value)
        expr = f"{v0}+({v1}-{v0})*(t-{t0})/({t1}-{t0})"
        if i == 0:
            segments.append(f"if(t<{t1},{expr}")
        else:
            segments.append(f",if(t<{t1},{expr}")
    return "".join(segments) + "," + str(float(kfs[-1].value)) + ")" * (len(kfs) - 1)


def normalize_track(
    keyframes: Sequence[Keyframe], duration_s: float
) -> List[Keyframe]:
    """Return a sanitized keyframe list clamped to ``[0, duration_s]``."""
    if not keyframes:
        return []
    dur = max(0.0, duration_s)
    out: List[Keyframe] = []
    for k in sorted(keyframes, key=lambda k: k.t_s):
        t = max(0.0, min(dur, float(k.t_s)))
        out.append(Keyframe(t_s=t, value=float(k.value), easing=getattr(k, "easing", "linear")))
    # Ensure endpoints exist.
    if out and out[0].t_s > 0:
        out.insert(0, Keyframe(t_s=0.0, value=out[0].value))
    if out and out[-1].t_s < dur:
        out.append(Keyframe(t_s=dur, value=out[-1].value))
    return out
