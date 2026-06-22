# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
# Commercial SaaS use is prohibited without written permission.
"""Generate cut-list using AI Provider abstraction layer."""

import json
import os
from typing import List, Dict, Any, Optional

# Add shared-py to path
import sys
repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
shared_py_path = os.path.join(repo_root, "shared-py", "src")
if shared_py_path not in sys.path:
    sys.path.insert(0, shared_py_path)

from shared_py.ai_providers.factory import get_ai_provider
from shared_py.logging_config import StructuredLogger
from shared_py.models import CutList, CutListGlobals, Slot, Overlay, Effect, BeatGrid, ShotBoundary, SectionMarker

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
                    "effects": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "type": {"type": "string", "enum": ["zoom_punch_in", "focus_pull", "freeze_frame", "speed_ramp", "shake", "glitch", "vignette", "film_grain", "color_pop", "text_kinetic", "lower_third", "callout_arrow", "whoosh_sfx", "ding_sfx", "record_scratch_sfx"]},
                                "startS": {"type": "number", "minimum": 0},
                                "durationS": {"type": "number", "minimum": 0},
                                "params": {"type": "object"},
                            },
                            "required": ["type", "startS", "durationS", "params"],
                        },
                    },
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


def _snap_time_to_shot_boundary(time_s: float, shot_boundaries: List[ShotBoundary], tolerance: float = 0.25) -> float:
    """Return the nearest shot-boundary start within ``tolerance`` seconds."""
    best = None
    best_dist = tolerance
    for shot in shot_boundaries:
        dist = abs(shot.start_s - time_s)
        if dist < best_dist:
            best_dist = dist
            best = shot.start_s
    return best if best is not None else time_s


def _next_beat_at_or_after(time_s: float, beats: List[float], eps: float = 1e-4) -> float:
    for beat in beats:
        if beat + eps >= time_s:
            return beat
    return beats[-1] if beats else time_s


def _shot_for_time(time_s: float, shot_boundaries: List[ShotBoundary]) -> Optional[ShotBoundary]:
    for shot in shot_boundaries:
        if shot.start_s <= time_s < shot.end_s:
            return shot
    return shot_boundaries[-1] if shot_boundaries else None


def _snap_slots_to_shots_and_beats(
    slots: List[Slot],
    shot_boundaries: List[ShotBoundary],
    beat_grid: BeatGrid,
    content_end: float,
) -> None:
    """Snap slot starts to the nearest shot boundary, then quantize duration to beats."""
    if not slots or not beat_grid.beats:
        return

    beats = beat_grid.beats
    beat_interval = 60.0 / beat_grid.bpm if beat_grid.bpm else 0.5

    for slot in slots:
        new_start = _snap_time_to_shot_boundary(slot.start_s, shot_boundaries)

        # Ensure we land on a beat grid line if the boundary moved us off it.
        closest_beat = min(beats, key=lambda b: abs(b - new_start))
        if abs(closest_beat - new_start) < 1e-3:
            new_start = closest_beat

        # Find the first beat that is strictly after the new start.
        next_beat = _next_beat_at_or_after(new_start + 1e-4, beats)
        duration = next_beat - new_start

        # Clamp duration to the end of the current shot and the content.
        shot = _shot_for_time(new_start, shot_boundaries)
        max_end = content_end
        if shot is not None:
            max_end = min(max_end, shot.end_s)

        # Extend by whole beat intervals while we stay inside the shot and below 2.5s.
        while (
            new_start + duration + beat_interval <= max_end + 1e-4
            and duration + beat_interval <= 2.5
        ):
            duration += beat_interval

        duration = min(duration, max_end - new_start)
        duration = max(duration, beat_interval)

        slot.start_s = round(new_start, 3)
        slot.duration_s = round(duration, 3)

        # Update beat_index to reflect the new start time.
        for i, beat in enumerate(beats):
            if abs(beat - slot.start_s) < 1e-3:
                slot.beat_index = i
                break

        # Keep effects inside the adjusted slot bounds.
        for effect in slot.effects:
            if effect.start_s < slot.start_s:
                effect.start_s = slot.start_s
            max_dur = slot.start_s + slot.duration_s - effect.start_s
            effect.duration_s = max(0.0, min(effect.duration_s, max_dur))

    # Final safety clamp on the last slot.
    if slots:
        slots[-1].duration_s = min(slots[-1].duration_s, content_end - slots[-1].start_s)


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
                beat_grid, shot_boundaries, energy_curve, available_shot_types, total_duration, style_analysis
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
        beat_grid, shot_boundaries, energy_curve, available_shot_types, total_duration, style_analysis
    )


def generate_cutlist_programmatic(
    beat_grid: BeatGrid,
    shot_boundaries: List[ShotBoundary],
    energy_curve: List[float],
    available_shot_types: List[str],
    total_duration: float = 30.0,
    style_analysis: Optional[Dict[str, Any]] = None,
) -> CutList:
    """Generate a cut-list programmatically without LLM."""
    style_analysis = style_analysis or {}
    detected_transitions = (
        style_analysis.get("detectedTransitions")
        or style_analysis.get("detected_transitions")
        or []
    )
    camera_motions = (
        style_analysis.get("cameraMotions")
        or style_analysis.get("camera_motions")
        or []
    )
    detected_overlays = (
        style_analysis.get("detectedOverlays")
        or style_analysis.get("detected_overlays")
        or []
    )

    # Bound the cutlist to the actual available shot content, not an arbitrary
    # total_duration that may exceed the source clips.
    max_shot_end = max((s.end_s for s in shot_boundaries), default=total_duration)
    content_end = min(total_duration, max_shot_end)

    beats = [b for b in beat_grid.beats if b <= content_end]
    downbeats = set(round(b, 2) for b in beat_grid.downbeats)
    segments = beat_grid.segments

    shot_pool = available_shot_types if available_shot_types else ["wide", "medium", "close_up"]

    slots = []
    overlays = []
    beat_idx = 0
    shot_rotation = 0
    last_cut_was_downbeat = False
    max_energy_slot = None
    section_change_beats = []  # track section boundaries for overlays/film_grain

    while beat_idx < len(beats) - 1 and beats[beat_idx] < content_end:
        beat_time = beats[beat_idx]
        next_beat = beats[beat_idx + 1] if beat_idx + 1 < len(beats) else content_end

        section = "intro"
        for seg in segments:
            if seg.start <= beat_time < seg.end:
                section = seg.label
                break

        progress = beat_time / content_end if content_end > 0 else 0.0
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
        if detected_transitions and energy > 0.4:
            transition_in = detected_transitions[len(slots) % len(detected_transitions)]

        transition_out = "hard_cut"

        next_section = "intro"
        for seg in segments:
            if seg.start <= next_beat < seg.end:
                next_section = seg.label
                break

        is_section_boundary = section != next_section
        if is_section_boundary and energy > 0.7:
            transition_out = "flash"
        elif is_downbeat and energy > 0.6:
            transition_out = "dissolve"
        elif detected_transitions and transition_out == "hard_cut" and energy > 0.5:
            transition_out = detected_transitions[(len(slots) + 1) % len(detected_transitions)]

        # Build effects for this slot
        effects = []
        if is_downbeat and energy > 0.7:
            effects.append(Effect(
                type="zoom_punch_in",
                start_s=beat_time,
                duration_s=min(0.3, duration),
                params={"target_scale": 1.25, "duration_ms": 250, "easing": "easeOut"},
            ))
        if energy < 0.4 and duration > 1.5:
            effects.append(Effect(
                type="focus_pull",
                start_s=beat_time + duration * 0.2,
                duration_s=min(0.8, duration * 0.6),
                params={"target_blur": 4.0, "duration_ms": 600, "easing": "easeInOut"},
            ))
        if is_section_boundary:
            effects.append(Effect(
                type="film_grain",
                start_s=beat_time,
                duration_s=duration,
                params={"intensity": 0.15},
            ))

        if camera_motions:
            motion_hint = camera_motions[len(slots) % len(camera_motions)]
        else:
            motion_hint = "static" if energy < 0.3 else "handheld" if energy > 0.8 else "gimbal"

        slot = Slot(
            index=len(slots),
            start_s=beat_time,
            duration_s=duration,
            beat_index=beat_idx,
            section=section,
            transition_in=transition_in,
            transition_out=transition_out,
            target_shot_type=target,
            subject_hint=f"{section} section, energy {energy:.1f}",
            motion_hint=motion_hint,
            energy_level=energy,
            required_tags=[],
            avoid_tags=[],
            effects=effects[:2],  # cap at 2 effects per slot
        )
        slots.append(slot)

        # Track highest-energy slot for vignette
        if max_energy_slot is None or energy > max_energy_slot.energy_level:
            max_energy_slot = slot

        # Section-boundary overlay
        if is_section_boundary and (not section_change_beats or section_change_beats[-1]["label"] != next_section):
            section_change_beats.append({"label": next_section.upper(), "start_s": next_beat})
            overlays.append(Overlay(
                text=next_section.upper(),
                start_s=max(0.0, next_beat - 0.2),
                end_s=min(content_end, next_beat + 1.5),
                position="top",
                font="Inter",
                font_size_px=48,
                color="#FFFFFF",
                stroke="#000000",
                animation="fade",
            ))

        beat_idx += 1
        if beat_time + duration >= content_end:
            break

    if slots:
        slots[-1].duration_s = min(slots[-1].duration_s, content_end - slots[-1].start_s)

    # Phase 2: snap slot starts to reference shot boundaries and re-quantize
    # durations so clip boundaries land on musical beats.
    _snap_slots_to_shots_and_beats(slots, shot_boundaries, beat_grid, content_end)

    # Overlays must not extend past the actual rendered content.
    actual_content_end = max(s.start_s + s.duration_s for s in slots) if slots else content_end

    # Add vignette to the highest-energy slot
    if max_energy_slot is not None:
        max_energy_slot.effects.append(Effect(
            type="vignette",
            start_s=max_energy_slot.start_s,
            duration_s=max_energy_slot.duration_s,
            params={"intensity": 0.4},
        ))
        # Re-apply cap in case we pushed it over 2
        if len(max_energy_slot.effects) > 2:
            max_energy_slot.effects = max_energy_slot.effects[:2]

    # Hook overlay at the very beginning if first slot is high-energy
    if slots and slots[0].energy_level > 0.6:
        overlays.insert(0, Overlay(
            text="LET'S GO",
            start_s=0.0,
            end_s=min(1.5, actual_content_end),
            position="center",
            font="Inter",
            font_size_px=64,
            color="#FFFFFF",
            stroke="#000000",
            animation="scale",
        ))

    # Outro CTA overlay in the final 2 seconds of actual content
    if slots and actual_content_end > 3.0:
        overlays.append(Overlay(
            text="FOLLOW FOR MORE",
            start_s=max(0.0, actual_content_end - 2.0),
            end_s=actual_content_end,
            position="bottom",
            font="Inter",
            font_size_px=42,
            color="#FFFFFF",
            stroke="#000000",
            animation="fade",
        ))

    # Add detected reference overlays (e.g., text/titles from the source video).
    for overlay in detected_overlays:
        if isinstance(overlay, Overlay):
            overlays.append(overlay)
        elif isinstance(overlay, dict):
            overlays.append(Overlay(
                text=overlay.get("text", ""),
                start_s=overlay.get("startS") or overlay.get("start_s", 0.0),
                end_s=overlay.get("endS") or overlay.get("end_s", actual_content_end),
                position=overlay.get("position", "center"),
                font=overlay.get("font") or overlay.get("fontFamily", "Inter"),
                font_size_px=overlay.get("fontSizePx") or overlay.get("font_size_px", 48),
                color=overlay.get("color", "#FFFFFF"),
                stroke=overlay.get("stroke", "#000000"),
                animation=overlay.get("animation", "fade"),
            ))

    # Clamp all overlays to actual content bounds
    for overlay in overlays:
        overlay.start_s = max(0.0, min(overlay.start_s, actual_content_end))
        overlay.end_s = max(overlay.start_s, min(overlay.end_s, actual_content_end))

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
        overlays=overlays,
    )
