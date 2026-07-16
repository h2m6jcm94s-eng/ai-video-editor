# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
# Commercial SaaS use is prohibited without written permission.
"""Generic keyframe interpolation helpers used by effects and layer compositing."""

import math
from typing import List, Sequence

from shared_py.models import Keyframe


# Spring tuned for ~5-8% overshoot and <2% settling by t=1.0.
_SPRING_DAMPING = 0.65
_SPRING_OMEGA = 10.0


def _spring_step(t: float) -> float:
    """Damped harmonic oscillator step response.

    Returns a value that starts at 0, overshoots ~1.06-1.08, then settles at 1.
    ``t`` is normalized to the keyframe interval [0, 1].
    """
    if t <= 0.0:
        return 0.0
    if t >= 1.0:
        return 1.0
    zeta = _SPRING_DAMPING
    omega = _SPRING_OMEGA
    omega_d = omega * math.sqrt(1.0 - zeta * zeta)
    envelope = math.exp(-zeta * omega * t)
    oscillation = math.cos(omega_d * t) + (zeta / math.sqrt(1.0 - zeta * zeta)) * math.sin(
        omega_d * t
    )
    return 1.0 - envelope * oscillation


def _ease(t: float, easing: str) -> float:
    """Apply an easing function to a normalized 0..1 value."""
    t = max(0.0, min(1.0, t))
    if easing == "linear":
        return t
    if easing == "ease_in":
        return t * t
    if easing == "ease_out":
        return 1.0 - (1.0 - t) * (1.0 - t)
    if easing == "ease_in_out":
        if t < 0.5:
            return 2.0 * t * t
        return 1.0 - math.pow(-2.0 * t + 2.0, 2.0) / 2.0
    if easing == "spring":
        return _spring_step(t)
    return t


def lerp(t: float, t0: float, t1: float, v0: float, v1: float) -> float:
    """Linear interpolation between two keyframe values (legacy easing-free)."""
    if t1 == t0:
        return float(v0)
    ratio = max(0.0, min(1.0, (t - t0) / (t1 - t0)))
    return float(v0) + ratio * (float(v1) - float(v0))


def sample(keyframes: Sequence[Keyframe], t: float) -> float:
    """Sample a scalar keyframe track at time ``t`` honoring each keyframe's easing."""
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
            if k1.t_s == k0.t_s:
                return float(k0.value)
            ratio = (t - k0.t_s) / (k1.t_s - k0.t_s)
            eased = _ease(ratio, getattr(k0, "easing", "linear"))
            return float(k0.value) + eased * (float(k1.value) - float(k0.value))
    return float(kfs[-1].value)


def _segment_expr(t0: float, t1: float, v0: float, v1: float, easing: str) -> str:
    """Return the FFmpeg expression for a single keyframe segment."""
    if easing == "linear":
        return f"{v0}+({v1}-{v0})*(t-{t0})/({t1}-{t0})"
    if easing == "ease_in":
        return f"{v0}+({v1}-{v0})*pow(((t-{t0})/({t1}-{t0})),2)"
    if easing == "ease_out":
        return f"{v0}+({v1}-{v0})*(1-pow(1-((t-{t0})/({t1}-{t0})),2))"
    if easing == "ease_in_out":
        return (
            f"{v0}+({v1}-{v0})*if(lt((t-{t0})/({t1}-{t0}),0.5),"
            f"2*pow((t-{t0})/({t1}-{t0}),2),"
            f"1-pow(-2*((t-{t0})/({t1}-{t0}))+2,2)/2)"
        )
    if easing == "spring":
        zeta = _SPRING_DAMPING
        omega = _SPRING_OMEGA
        omega_d = omega * math.sqrt(1.0 - zeta * zeta)
        ratio_expr = f"((t-{t0})/({t1}-{t0}))"
        damp_str = f"{zeta:.6f}"
        omega_str = f"{omega:.6f}"
        omega_d_str = f"{omega_d:.6f}"
        zeta_sqrt = zeta / math.sqrt(1.0 - zeta * zeta)
        return (
            f"{v0}+({v1}-{v0})*"
            f"(1-exp(-{damp_str}*{omega_str}*{ratio_expr})*"
            f"(cos({omega_d_str}*{ratio_expr})+{zeta_sqrt:.6f}*sin({omega_d_str}*{ratio_expr})))"
        )
    return base


def ffmpeg_expression(keyframes: Sequence[Keyframe]) -> str:
    """Build an FFmpeg expression string that interpolates keyframes over ``t``.

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
        easing = getattr(kfs[i], "easing", "linear")
        expr = _segment_expr(t0, t1, v0, v1, easing)
        if i == 0:
            segments.append(f"if(t<{t1},{expr}")
        else:
            segments.append(f",if(t<{t1},{expr}")
    return "".join(segments) + "," + str(float(kfs[-1].value)) + ")" * (len(kfs) - 1)


def normalize_track(
    keyframes: Sequence[Keyframe], duration_s: float, default_easing: str = "linear"
) -> List[Keyframe]:
    """Return a sanitized keyframe list clamped to ``[0, duration_s]``.

    Missing easing values are filled with ``default_easing``.
    """
    if not keyframes:
        return []
    dur = max(0.0, duration_s)
    out: List[Keyframe] = []
    for k in sorted(keyframes, key=lambda k: k.t_s):
        t = max(0.0, min(dur, float(k.t_s)))
        current = getattr(k, "easing", "linear")
        # If the keyframe carries the model default "linear", allow the caller's
        # default_easing to override it (e.g. spring for text layers).
        easing = default_easing if current == "linear" else current
        out.append(Keyframe(t_s=t, value=float(k.value), easing=easing))
    # Ensure endpoints exist.
    if out and out[0].t_s > 0:
        out.insert(0, Keyframe(t_s=0.0, value=out[0].value, easing=default_easing))
    if out and out[-1].t_s < dur:
        out.append(Keyframe(t_s=dur, value=out[-1].value, easing=default_easing))
    return out
