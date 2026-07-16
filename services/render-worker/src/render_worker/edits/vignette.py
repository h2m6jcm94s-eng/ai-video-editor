# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
"""Vignette filter primitive for darkening the frame edges."""

from __future__ import annotations


def vignette_filter(
    rel_start: float,
    rel_end: float,
    intensity: float = 0.4,
) -> str:
    """Return an FFmpeg vignette filter enabled over the effect window."""
    return (
        f"vignette=PI/{max(0.01, 1 - intensity)}:"
        f"enable='between(t\\,{rel_start:.3f}\\,{rel_end:.3f})'"
    )
