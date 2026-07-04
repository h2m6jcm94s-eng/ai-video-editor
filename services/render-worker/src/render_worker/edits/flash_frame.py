# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
"""White flash-frame compositor primitive for impact cuts."""

from __future__ import annotations


def flash_frame_filter(start_s: float, duration_s: float, fps: float = 30.0) -> str:
    """Return an FFmpeg filter clause that paints one white frame.

    The implementation uses ``drawbox`` because the filter chain is a single
    input; a generated ``color`` source would require a second input stream.
    The flash duration defaults to one frame.
    """
    if duration_s <= 0.0:
        duration_s = 1.0 / max(fps, 1.0)
    end_s = start_s + duration_s
    return (
        f"drawbox=x=0:y=0:w=iw:h=ih:color=white:t=fill"
        f":enable='between(t\\,{start_s:.4f}\\,{end_s:.4f})'"
    )
