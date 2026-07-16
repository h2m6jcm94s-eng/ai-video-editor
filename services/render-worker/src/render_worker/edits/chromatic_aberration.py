# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
"""Chromatic aberration filter primitive using per-channel RGB shifts."""

from __future__ import annotations


def chromatic_aberration_filter(
    rel_start: float,
    rel_end: float,
    shift_x: int = 3,
    shift_y: int = 0,
    intensity: float = 0.3,
) -> str:
    """Return an FFmpeg rgbashift filter enabled over the effect window.

    ``intensity`` scales the requested shifts so the same params can be used
    for subtle or exaggerated fringing.
    """
    sx = max(1, int(shift_x * (0.5 + intensity)))
    sy = max(0, int(shift_y * (0.5 + intensity)))
    return (
        f"rgbashift=rh={sx}:gh=-{sx}:bv={sy}:"
        f"enable='between(t\\,{rel_start:.3f}\\,{rel_end:.3f})'"
    )
