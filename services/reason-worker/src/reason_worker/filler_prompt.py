# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
# Commercial SaaS use is prohibited without written permission.
"""Prompt builder for generative filler/transition clips.

Filler clips are short generative videos used when no user clip strongly
matches a slot (low ranking confidence) or when an explicit transition is
needed between sections.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from shared_py.models import Slot


# Shot-type → natural-language framing guidance.
_SHOT_GUIDE = {
    "extreme_wide": "extreme wide shot, vast environment, tiny subject",
    "wide": "wide shot, full subject and surrounding environment",
    "medium_wide": "medium-wide shot, subject from the knees up with context",
    "medium": "medium shot, subject from the waist up",
    "medium_close_up": "medium close-up, subject from the chest up",
    "close_up": "close-up, subject's face or key detail fills the frame",
    "extreme_close_up": "extreme close-up, a single expressive detail",
    "insert": "insert shot, cutaway detail or prop",
    "establishing": "establishing shot, location and context",
}

# Motion hint → camera/movement language.
_MOTION_GUIDE = {
    "static": "locked-off tripod, no camera movement",
    "slow_push": "slow gentle push in",
    "fast_push": "fast aggressive push in",
    "pull": "slow pull back",
    "pan_left": "smooth pan left",
    "pan_right": "smooth pan right",
    "tilt_up": "smooth tilt up",
    "tilt_down": "smooth tilt down",
    "whip": "fast whip pan",
    "zoom_in": "snap zoom in",
    "zoom_out": "snap zoom out",
    "dolly_in": "dolly in",
    "dolly_out": "dolly out",
    "tracking": "tracking shot following the subject",
    "handheld": "subtle handheld documentary feel",
    "gimbal": "fluid gimbal movement",
    "drone": "aerial drone movement",
    "crane": "sweeping crane movement",
    "speed_ramp": "speed ramp from slow to fast",
    "freeze": "frozen moment, still frame feel",
}

_TRANSITION_GUIDE = {
    "fade": "gentle fade-friendly motion, soft lighting",
    "dissolve": "dreamy dissolve-friendly motion, avoid hard edges",
    "wipe_left": "horizontal motion from right to left",
    "wipe_right": "horizontal motion from left to right",
    "wipe_up": "vertical motion from bottom to top",
    "wipe_down": "vertical motion from top to bottom",
    "circle_open": "radial outward motion or reveal",
    "slide_up": "upward motion or lift",
    "slide_down": "downward motion or drop",
    "slide_left": "leftward motion",
    "slide_right": "rightward motion",
    "pixelize": "abstract digital glitch-friendly motion",
    "hlslice": "hard light slice-friendly high-contrast motion",
    "flash": "brief bright flash-friendly motion",
    "whip": "fast whip-friendly motion",
}


def build_filler_prompt(
    slot: Slot,
    style_analysis: Optional[Dict[str, Any]] = None,
    transition_context: Optional[str] = None,
) -> str:
    """Create a detailed generative-video prompt for a single slot.

    Args:
        slot: The cut-list slot to generate a clip for.
        style_analysis: Style analysis dict from ``analyze_reference_style``.
        transition_context: Optional description of the preceding/following shot
            to make the filler blend (e.g. "from forest trail to city rooftop").
    """
    style_analysis = style_analysis or {}

    shot = _SHOT_GUIDE.get(slot.target_shot_type, slot.target_shot_type)
    motion = _MOTION_GUIDE.get(slot.motion_hint, slot.motion_hint)

    parts = [
        f"Cinematic {shot}.",
        f"Subject: {slot.subject_hint or 'the main subject'}.",
        f"Camera: {motion}.",
    ]

    if slot.transition_in in _TRANSITION_GUIDE:
        parts.append(f"Transition in: {_TRANSITION_GUIDE[slot.transition_in]}.")
    if slot.transition_out in _TRANSITION_GUIDE:
        parts.append(f"Transition out: {_TRANSITION_GUIDE[slot.transition_out]}.")

    energy = max(0.0, min(1.0, slot.energy_level or 0.5))
    if energy > 0.7:
        parts.append("High energy, fast pacing, bold lighting.")
    elif energy > 0.4:
        parts.append("Moderate energy, balanced natural lighting.")
    else:
        parts.append("Low energy, calm mood, soft lighting.")

    if slot.required_tags:
        parts.append(f"Must include: {', '.join(slot.required_tags)}.")
    if slot.avoid_tags:
        parts.append(f"Avoid: {', '.join(slot.avoid_tags)}.")

    palette = style_analysis.get("color_palette")
    if palette:
        parts.append(f"Color palette: {palette}.")
    contrast = style_analysis.get("contrast_level")
    saturation = style_analysis.get("saturation_level")
    if contrast is not None and saturation is not None:
        parts.append(f"Look: {contrast:.0%} contrast, {saturation:.0%} saturation.")

    if transition_context:
        parts.append(f"Continuity: {transition_context}.")

    parts.append("Photorealistic, 720p, smooth 30fps, no text, no watermarks.")
    return " ".join(parts)


def build_transition_prompt(
    from_slot: Optional[Slot],
    to_slot: Optional[Slot],
    style_analysis: Optional[Dict[str, Any]] = None,
) -> str:
    """Build a prompt that bridges two slots for a transition filler."""
    from_desc = from_slot.subject_hint if from_slot else "previous scene"
    to_desc = to_slot.subject_hint if to_slot else "next scene"
    context = f"transition from {from_desc} to {to_desc}"

    shot = "medium wide shot" if to_slot is None else _SHOT_GUIDE.get(to_slot.target_shot_type, to_slot.target_shot_type)
    transition_in = from_slot.transition_out if from_slot else "hard_cut"
    transition_out = to_slot.transition_in if to_slot else "hard_cut"

    parts = [
        f"Cinematic transition clip, {shot}.",
        f"Starts with {from_desc}, ends with {to_desc}.",
    ]
    if transition_in in _TRANSITION_GUIDE:
        parts.append(f"Transition in style: {_TRANSITION_GUIDE[transition_in]}.")
    if transition_out in _TRANSITION_GUIDE:
        parts.append(f"Transition out style: {_TRANSITION_GUIDE[transition_out]}.")

    target_slot = to_slot or Slot(
        index=-1,
        start_s=0.0,
        duration_s=2.0,
        beat_index=0,
        section="transition",
        target_shot_type="medium_wide",
        subject_hint=context,
        motion_hint="gimbal",
    )
    return build_filler_prompt(
        slot=target_slot,
        style_analysis=style_analysis,
        transition_context=context,
    )
