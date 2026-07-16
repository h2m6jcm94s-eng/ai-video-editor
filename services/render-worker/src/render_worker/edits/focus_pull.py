# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
"""Focus pull filter primitive using a ramped Gaussian blur."""

from __future__ import annotations

from typing import List


def focus_pull_filter(
    rel_start: float,
    rel_end: float,
    target_blur: float = 4.0,
    duration_ms: int = 600,
    fps: float = 30.0,
) -> List[str]:
    """Return FFmpeg gblur filters that ramp blur up over the effect window.

    Because ``gblur`` sigma is constant, we chain two passes of increasing
    strength to approximate a smooth ramp.
    """
    dur = min(duration_ms / 1000.0, rel_end - rel_start)
    mid = rel_start + dur * 0.5
    return [
        f"gblur=sigma={target_blur * 0.4:.2f}:steps=1:"
        f"enable='between(t\\,{rel_start:.3f}\\,{mid:.3f})'",
        f"gblur=sigma={target_blur:.2f}:steps=2:"
        f"enable='between(t\\,{mid:.3f}\\,{rel_start + dur:.3f})'",
    ]
