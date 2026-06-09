# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
# Commercial SaaS use is prohibited without written permission.
"""Generate cut-list using AI Provider abstraction layer."""

import json
import os
from typing import List, Dict, Any

# Add shared-py to path
import sys
repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
shared_py_path = os.path.join(repo_root, "shared-py", "src")
if shared_py_path not in sys.path:
    sys.path.insert(0, shared_py_path)

from shared_py.ai_providers.factory import get_ai_provider
from shared_py.logging_config import StructuredLogger
from shared_py.models import CutList, CutListGlobals, Slot, Overlay, BeatGrid, ShotBoundary, SectionMarker

logger = StructuredLogger("reason_worker.cutlist_gen")


CUTLIST_SCHEMA = {
    "type": "object",
    "properties": {
        "globals": {
            "type": "object",
            "properties": {
                "totalDurationS": {"type": "number"},
                "tempoBpm": {"type": "number"},
                "timeSignature": {"type": "string"},
                "key": {"type": "string"},
                "energyCurve": {"type": "array", "items": {"type": "number"}},
                "sectionMarkers": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "startS": {"type": "number"},
                            "endS": {"type": "number"},
                        },
                        "required": ["name", "startS", "endS"],
                    },
                },
                "colorGradeRef": {"type": "string"},
                "aspectRatio": {"type": "string"},
            },
            "required": ["totalDurationS", "tempoBpm", "timeSignature", "energyCurve", "sectionMarkers", "aspectRatio"],
        },
        "slots": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "index": {"type": "integer"},
                    "startS": {"type": "number"},
                    "durationS": {"type": "number"},
                    "beatIndex": {"type": "integer"},
                    "section": {"type": "string"},
                    "transitionIn": {"type": "string", "enum": ["hard_cut", "fade", "dissolve", "wipe_left", "wipe_right", "wipe_up", "wipe_down", "circle_open", "slide_up", "slide_down", "slide_left", "slide_right", "pixelize", "hlslice", "flash", "whip"]},
                    "transitionOut": {"type": "string", "enum": ["hard_cut", "fade", "dissolve", "wipe_left", "wipe_right", "wipe_up", "wipe_down", "circle_open", "slide_up", "slide_down", "slide_left", "slide_right", "pixelize", "hlslice", "flash", "whip"]},
                    "targetShotType": {"type": "string", "enum": ["extreme_wide", "wide", "medium_wide", "medium", "medium_close_up", "close_up", "extreme_close_up", "insert", "establishing"]},
                    "subjectHint": {"type": "string"},
                    "motionHint": {"type": "string", "enum": ["static", "slow_push", "fast_push", "pull", "pan_left", "pan_right", "tilt_up", "tilt_down", "whip", "zoom_in", "zoom_out", "dolly_in", "dolly_out", "tracking", "handheld", "gimbal", "drone", "crane", "speed_ramp", "freeze"]},
                    "energyLevel": {"type": "number", "minimum": 0, "maximum": 1},
                    "requiredTags": {"type": "array", "items": {"type": "string"}},
                    "avoidTags": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["index", "startS", "durationS", "beatIndex", "section", "transitionIn", "transitionOut", "targetShotType", "subjectHint", "motionHint", "energyLevel", "requiredTags", "avoidTags"],
            },
        },
        "overlays": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "startS": {"type": "number"},
                    "endS": {"type": "number"},
                    "position": {"type": "string", "enum": ["center", "top", "bottom", "left", "right", "top_left", "top_right", "bottom_left", "bottom_right"]},
                    "font": {"type": "string"},
                    "fontSizePx": {"type": "integer"},
                    "color": {"type": "string"},
                    "stroke": {"type": "string"},
                    "animation": {"type": "string", "enum": ["none", "fade", "slide", "typewriter", "scale", "pop", "word_by_word"]},
                },
                "required": ["text", "startS", "endS", "position", "font", "fontSizePx", "color", "animation"],
            },
        },
    },
    "required": ["globals", "slots", "overlays"],
}


def generate_cutlist(
    beat_grid: BeatGrid,
    shot_boundaries: List[ShotBoundary],
    style_analysis: Dict[str, Any],
    energy_curve: List[float],
    available_shot_types: List[str],
    total_duration: float = 30.0,
) -> CutList:
    """Generate a cut-list using the configured AI provider chain.

    Supports comma-separated fallback chain via AI_PROVIDER env var:
        AI_PROVIDER=kimi,qwen,programmatic
    Programmatic is always the final fallback if the chain exhausts.
    """
    provider_chain = os.environ.get("AI_PROVIDER", "programmatic")
    names = [n.strip() for n in provider_chain.split(",") if n.strip()]

    for name in names:
        if name == "programmatic":
            return generate_cutlist_programmatic(
                beat_grid, shot_boundaries, energy_curve, available_shot_types, total_duration
            )

        try:
            provider = get_ai_provider(name)
            context = provider._build_cutlist_context(
                beat_grid, shot_boundaries, style_analysis, energy_curve, available_shot_types, total_duration
            )
            return provider.generate_cutlist(context, CUTLIST_SCHEMA)
        except Exception as e:
            logger.warning("AI provider failed, trying next", provider=name, error=str(e))
            continue

    logger.warning("All AI providers exhausted, falling back to programmatic")
    return generate_cutlist_programmatic(
        beat_grid, shot_boundaries, energy_curve, available_shot_types, total_duration
    )


def generate_cutlist_programmatic(
    beat_grid: BeatGrid,
    shot_boundaries: List[ShotBoundary],
    energy_curve: List[float],
    available_shot_types: List[str],
    total_duration: float = 30.0,
) -> CutList:
    """Generate a cut-list programmatically without LLM."""
    beats = [b for b in beat_grid.beats if b <= total_duration]
    downbeats = set(round(b, 2) for b in beat_grid.downbeats)
    segments = beat_grid.segments

    shot_pool = available_shot_types if available_shot_types else ["wide", "medium", "close_up"]

    slots = []
    beat_idx = 0
    shot_rotation = 0
    last_cut_was_downbeat = False

    while beat_idx < len(beats) - 1 and beats[beat_idx] < total_duration:
        beat_time = beats[beat_idx]
        next_beat = beats[beat_idx + 1] if beat_idx + 1 < len(beats) else total_duration

        section = "intro"
        for seg in segments:
            if seg.start <= beat_time < seg.end:
                section = seg.label
                break

        progress = beat_time / total_duration
        energy_idx = min(int(progress * len(energy_curve)), len(energy_curve) - 1)
        energy = energy_curve[energy_idx] if energy_curve else 0.5

        is_downbeat = round(beat_time, 2) in downbeats
        if is_downbeat and not last_cut_was_downbeat:
            duration = min(next_beat - beat_time + 0.5, 2.5)
            last_cut_was_downbeat = True
        else:
            duration = min(next_beat - beat_time, 1.5)
            last_cut_was_downbeat = False

        duration = max(duration, 0.5)

        if energy < 0.3:
            target = "wide" if "wide" in shot_pool else shot_pool[0]
        elif energy < 0.6:
            target = "medium" if "medium" in shot_pool else shot_pool[shot_rotation % len(shot_pool)]
        elif energy < 0.8:
            target = "medium_close_up" if "medium_close_up" in shot_pool else "close_up" if "close_up" in shot_pool else shot_pool[-1]
        else:
            target = "close_up" if "close_up" in shot_pool else shot_pool[-1]

        shot_rotation += 1

        transition_in = "hard_cut"
        transition_out = "hard_cut"

        next_section = "intro"
        for seg in segments:
            if seg.start <= next_beat < seg.end:
                next_section = seg.label
                break

        if section != next_section and energy > 0.7:
            transition_out = "flash"
        elif is_downbeat and energy > 0.6:
            transition_out = "dissolve"

        slots.append(Slot(
            index=len(slots),
            start_s=beat_time,
            duration_s=duration,
            beat_index=beat_idx,
            section=section,
            transition_in=transition_in,
            transition_out=transition_out,
            target_shot_type=target,
            subject_hint=f"{section} section, energy {energy:.1f}",
            motion_hint="static" if energy < 0.3 else "handheld" if energy > 0.8 else "gimbal",
            energy_level=energy,
            required_tags=[],
            avoid_tags=[],
        ))

        beat_idx += 1
        if beat_time + duration >= total_duration:
            break

    if slots:
        slots[-1].duration_s = min(slots[-1].duration_s, total_duration - slots[-1].start_s)

    return CutList(
        globals=CutListGlobals(
            total_duration_s=total_duration,
            tempo_bpm=beat_grid.bpm,
            time_signature="4/4",
            energy_curve=energy_curve,
            section_markers=[
                SectionMarker(name=s.label, start_s=s.start, end_s=s.end)
                for s in segments
            ],
            aspect_ratio="9:16",
        ),
        slots=slots,
        overlays=[],
    )
