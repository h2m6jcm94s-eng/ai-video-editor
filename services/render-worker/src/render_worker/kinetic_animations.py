# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
"""Centralised kinetic-text animation registry.

Wave 8 backfill: the reason worker picks an animation name from this table,
and the render worker maps that name to either a drawtext expression or an
ASS subtitle directive. Keeping the registry in one place prevents the
reason/render sides from drifting.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Set


@dataclass(frozen=True)
class AnimationPreset:
    """Metadata for one kinetic-text animation."""

    name: str
    family: str  # "impact", "cinematic", "lyric", "glitch"
    requires_ass: bool
    default_in_ms: int = 150
    default_hold_ms: int = 600
    default_out_ms: int = 200
    # Whether the animation works well when text is composited behind a subject matte.
    safe_behind_subject: bool = False


# Canonical animation names. These strings cross the reason/render boundary.
KINETIC_ANIMATIONS: Dict[str, AnimationPreset] = {
    "pop": AnimationPreset(
        name="pop",
        family="impact",
        requires_ass=False,
        default_in_ms=100,
        default_hold_ms=800,
        default_out_ms=150,
    ),
    "scale": AnimationPreset(
        name="scale",
        family="impact",
        requires_ass=False,
        default_in_ms=120,
        default_hold_ms=800,
        default_out_ms=180,
    ),
    "punch_in_3f": AnimationPreset(
        name="punch_in_3f",
        family="impact",
        requires_ass=False,
        default_in_ms=100,
        default_hold_ms=900,
        default_out_ms=150,
    ),
    "shake_3f": AnimationPreset(
        name="shake_3f",
        family="impact",
        requires_ass=False,
        default_in_ms=100,
        default_hold_ms=700,
        default_out_ms=150,
    ),
    "fade": AnimationPreset(
        name="fade",
        family="cinematic",
        requires_ass=False,
        default_in_ms=300,
        default_hold_ms=1000,
        default_out_ms=300,
        safe_behind_subject=True,
    ),
    "typewriter": AnimationPreset(
        name="typewriter",
        family="cinematic",
        requires_ass=False,
        default_in_ms=400,
        default_hold_ms=1200,
        default_out_ms=200,
    ),
    "glitch": AnimationPreset(
        name="glitch",
        family="glitch",
        requires_ass=False,
        default_in_ms=100,
        default_hold_ms=700,
        default_out_ms=200,
    ),
    "bold_bounce": AnimationPreset(
        name="bold_bounce",
        family="impact",
        requires_ass=False,
        default_in_ms=100,
        default_hold_ms=900,
        default_out_ms=150,
        safe_behind_subject=True,
    ),
    "karaoke_reveal": AnimationPreset(
        name="karaoke_reveal",
        family="lyric",
        requires_ass=True,
        default_in_ms=100,
        default_hold_ms=0,  # per-word hold
        default_out_ms=100,
        safe_behind_subject=True,
    ),
}

# Subset used for global kinetic-text overlays (not karaoke captions).
KINETIC_TEXT_ANIMATIONS: List[str] = [
    "pop",
    "scale",
    "punch_in_3f",
    "shake_3f",
    "fade",
    "typewriter",
    "glitch",
    "bold_bounce",
]


def preset(name: str) -> Optional[AnimationPreset]:
    """Return a preset by canonical name."""
    return KINETIC_ANIMATIONS.get(name)


def is_ass_only(name: str) -> bool:
    """True if the animation must be rendered via ASS subtitles."""
    p = KINETIC_ANIMATIONS.get(name)
    return p.requires_ass if p else False


def supported_animations() -> Set[str]:
    return set(KINETIC_ANIMATIONS.keys())


def default_for_style(style_preset: str, energy: float = 0.7) -> str:
    """Fallback mapping from style preset to animation when no explicit pick was made."""
    if style_preset in ("anime_impact", "stamp_white"):
        return "scale" if energy >= 0.75 else "pop"
    if style_preset == "neon_glitch":
        return "glitch"
    if style_preset in ("cinematic_serif", "lowercase_intimate"):
        return "fade"
    if style_preset in ("trailer_block", "handwritten_pen"):
        return "typewriter"
    if style_preset == "shake_emphasis":
        return "shake_3f"
    return "pop"
