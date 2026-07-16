# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
"""Pick a kinetic-text animation for a slot from the Wave 8 animation table.

The table is intentionally small and interpretable: energy + style + placement
(face behind subject vs on top) drive the choice. The render worker validates
that the returned name exists in its `kinetic_animations` registry.
"""

from __future__ import annotations

from shared_py.models import Slot


def choose_kinetic_animation(
    slot: Slot,
    style_preset: str,
    face_present: bool = False,
) -> str:
    """Return the canonical animation name for this slot's kinetic text."""
    # Lyric-driven karaoke reveal is selected explicitly by the composer.
    if style_preset == "lyric_karaoke":
        return "karaoke_reveal"

    energy = float(getattr(slot, "energy_level", 0.5) or 0.5)
    section = (getattr(slot, "section", "") or "").lower()
    is_drop = section in ("drop", "chorus", "bridge")
    is_calm = section in ("intro", "verse", "break") or energy < 0.4

    # Text composited behind a subject matte should not jump around.
    if face_present or getattr(slot, "text_z_layer", "on_top") == "behind_subject":
        if style_preset in ("cinematic_serif", "lowercase_intimate"):
            return "fade"
        if energy > 0.75 and style_preset in ("anime_impact", "stamp_white"):
            return "bold_bounce"
        return "fade"

    # High-energy impact moments.
    if energy >= 0.8 and is_drop:
        if style_preset == "shake_emphasis":
            return "shake_3f"
        if style_preset == "neon_glitch":
            return "glitch"
        return "punch_in_3f"

    if energy >= 0.65:
        if style_preset == "neon_glitch":
            return "glitch"
        if style_preset in ("anime_impact", "stamp_white"):
            return "scale"
        if style_preset == "shake_emphasis":
            return "shake_3f"
        return "pop"

    # Calm / cinematic moments.
    if is_calm or energy < 0.45:
        if style_preset in ("trailer_block", "handwritten_pen"):
            return "typewriter"
        if style_preset in ("cinematic_serif", "lowercase_intimate"):
            return "fade"
        return "fade"

    # Default energy mid-range.
    if style_preset in ("trailer_block", "handwritten_pen"):
        return "typewriter"
    if style_preset in ("cinematic_serif", "lowercase_intimate"):
        return "fade"
    if style_preset == "neon_glitch":
        return "glitch"
    return "pop"
