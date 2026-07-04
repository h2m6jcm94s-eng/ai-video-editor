# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
# Commercial SaaS use is prohibited without written permission.
"""Mood/energy-aware font selection for on-screen text.

All returned families map to bundled cinematic fonts so renders stay
portable and the ``non_system_font`` golden gate stays green.
"""

from __future__ import annotations

from typing import Optional


def select_font_for_mood(mood: Optional[str], energy: float) -> str:
    """Return a bundled font family name matching the moment.

    The mapping is intentionally deterministic so tests and renders are stable.
    """
    mood_l = (mood or "").lower()

    aggressive = {
        "aggressive",
        "anger",
        "angry",
        "intense",
        "aggression",
        "furious",
        "rage",
        "violent",
        "chaotic",
        "power",
        "heavy",
    }
    melancholic = {
        "melancholic",
        "melancholy",
        "sad",
        "somber",
        "grief",
        "grieving",
        "fear",
        "afraid",
        "tense",
        "lonely",
        "intimate",
        "nostalgic",
    }

    if any(token in mood_l for token in aggressive) or energy > 0.75:
        return "Anton"
    if any(token in mood_l for token in melancholic) or energy < 0.35:
        return "Cinzel"
    return "Montserrat"
