# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
"""Detect the closest export preset from reference video dimensions."""

from typing import Optional


ASPECT_PRESETS = {
    "youtube_16_9": (1920, 1080),
    "reels_9_16": (1080, 1920),
    "square_1_1": (1080, 1080),
    "cinema_2_35": (2048, 858),
}


def detect_aspect_preset(width: Optional[int], height: Optional[int]) -> str:
    """Pick the closest export preset for the given reference dimensions.

    Falls back to ``youtube_16_9`` when dimensions are missing or ambiguous.
    """
    if not width or not height:
        return "youtube_16_9"

    ratio = width / height

    if 1.6 <= ratio <= 1.95:  # 16:9, 16:10, 1.85:1
        return "youtube_16_9"
    if 0.5 <= ratio <= 0.63:  # 9:16
        return "reels_9_16"
    if 0.9 <= ratio <= 1.1:  # 1:1
        return "square_1_1"
    if ratio >= 2.2:  # anamorphic / 2.35:1+
        return "cinema_2_35"

    # Default landscape for anything else (4:3, 21:9, etc.).
    return "youtube_16_9"
