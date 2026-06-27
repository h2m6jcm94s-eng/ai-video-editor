# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
# Commercial SaaS use is prohibited without written permission.
"""Generate cut-list using AI Provider abstraction layer."""

import os
from typing import List, Dict, Any, Optional

# Add shared-py to path
import sys
repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
shared_py_path = os.path.join(repo_root, "shared-py", "src")
if shared_py_path not in sys.path:
    sys.path.insert(0, shared_py_path)

from shared_py.ai_providers.factory import get_ai_provider
from shared_py.config import settings
from shared_py.logging_config import StructuredLogger
from shared_py.models import (
    CutList, CutListGlobals, Slot, Overlay, Effect, BeatGrid, ShotBoundary, SectionMarker, AudioTrack,
    ZoomPunchInParams, FocusPullParams, FilmGrainParams, VignetteParams,
)

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


def _nearest_shot_within(
    time_s: float, shot_boundaries: List[ShotBoundary], tolerance: float
) -> Optional[float]:
    """Return the nearest shot-boundary start within ``tolerance`` seconds."""
    best = None
    best_dist = tolerance
    for shot in shot_boundaries:
        dist = abs(shot.start_s - time_s)
        if dist < best_dist:
            best_dist = dist
            best = shot.start_s
    return best


def _snap_slots_to_shots_and_beats(
    slots: List[Slot],
    shot_boundaries: List[ShotBoundary],
    beat_grid: BeatGrid,
    content_end: float,
    downbeat_lock_radius: float = 0.10,
    beat_prefer_radius: float = 0.05,
) -> None:
    """Snap slot starts to shot boundaries and ensure slots do not overlap or exceed content.

    Uses tiered beat importance:
    - Downbeats within ``downbeat_lock_radius`` are locked, ignoring shot boundaries.
    - Regular beats within ``beat_prefer_radius`` are preferred, yielding only to shots
      within the same small radius.
    - Otherwise fall back to the original shot-boundary snap behavior.
    """
    if not slots or not beat_grid.beats:
        return

    beats = beat_grid.beats
    downbeats = getattr(beat_grid, "downbeats", []) or []
    beat_interval = 60.0 / beat_grid.bpm if beat_grid.bpm else 0.5

    # Snap starts and drop anything that falls past the content.
    snapped = []
    for slot in slots:
        # Tiered snap: downbeat > beat > shot.
        nearest_downbeat_dist = min((abs(slot.start_s - d) for d in downbeats), default=float("inf"))
        nearest_beat_dist = min((abs(slot.start_s - b) for b in beats), default=float("inf"))
        nearest_downbeat = min(downbeats, key=lambda d: abs(d - slot.start_s)) if downbeats else None
        nearest_beat = min(beats, key=lambda b: abs(b - slot.start_s)) if beats else None

        if nearest_downbeat is not None and nearest_downbeat_dist < downbeat_lock_radius:
            new_start = nearest_downbeat
        elif nearest_beat is not None and nearest_beat_dist < beat_prefer_radius:
            new_start = nearest_beat
            shot = _nearest_shot_within(new_start, shot_boundaries, beat_prefer_radius)
            if shot is not None:
                new_start = shot
        else:
            new_start = _snap_time_to_shot_boundary(slot.start_s, shot_boundaries)

        new_start = round(max(0.0, min(new_start, content_end)), 3)
        if new_start >= content_end - 1e-4:
            continue

        slot.start_s = new_start

        # Update beat_index to reflect the new start time.
        for i, beat in enumerate(beats):
            if abs(beat - slot.start_s) < 1e-3:
                slot.beat_index = i
                break

        snapped.append(slot)

    slots[:] = snapped
    if not slots:
        return

    # Sort by start time and make slots contiguous up to the next slot or
    # content end, while respecting shot boundaries and a 4.0s max slot length.
    slots.sort(key=lambda s: s.start_s)
    for i, slot in enumerate(slots):
        # Indices must reflect the final sorted order so downstream code (clip
        # ranking, mask lookup, etc.) can rely on index == position.
        slot.index = i

        next_start = slots[i + 1].start_s if i + 1 < len(slots) else content_end
        max_end = min(content_end, next_start)

        # Extend the slot to fill the available contiguous region up to the next
        # slot or content end, but keep it at least one beat long and no longer
        # than 4.0s. We no longer truncate at reference shot boundaries because
        # that produces too many tiny slots when beats and shots interleave.
        available = max_end - slot.start_s
        if available <= 1e-4:
            # Slot has no room; give it a minimal beat-long window if possible.
            slot.duration_s = round(min(beat_interval, content_end - slot.start_s), 3)
        else:
            duration = max(beat_interval, min(available, 4.0))
            duration = min(duration, available)
            slot.duration_s = round(duration, 3)

        # Keep effects inside the adjusted slot bounds.
        for effect in slot.effects:
            if effect.start_s < slot.start_s:
                effect.start_s = slot.start_s
            max_dur = max(0.0, slot.start_s + slot.duration_s - effect.start_s)
            effect.duration_s = max(0.0, min(effect.duration_s, max_dur))

    # Drop any slots that still collapsed to zero or negative duration.
    slots[:] = [s for s in slots if s.duration_s > 0.05]
    for i, slot in enumerate(slots):
        slot.index = i


STYLE_TIERS = ("cuts_only", "color_grade", "with_text", "with_effects", "full_remix")


def _tier_index(tier: str) -> int:
    try:
        return STYLE_TIERS.index(tier)
    except ValueError:
        return len(STYLE_TIERS) - 1


def generate_cutlist(
    beat_grid: BeatGrid,
    shot_boundaries: List[ShotBoundary],
    style_analysis: Dict[str, Any],
    energy_curve: List[float],
    available_shot_types: List[str],
    total_duration: float = 30.0,
    style_tier: str = "full_remix",
    song_asset_id: Optional[str] = None,
    user_clip_count: Optional[int] = None,
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
                beat_grid, shot_boundaries, energy_curve, available_shot_types, total_duration,
                style_analysis, style_tier, song_asset_id, user_clip_count,
            )

        try:
            provider = get_ai_provider(name)
            context = provider._build_cutlist_context(
                beat_grid, shot_boundaries, style_analysis, energy_curve, available_shot_types, total_duration
            )
            cutlist = provider.generate_cutlist(context, CUTLIST_SCHEMA)
            # Attach the song to AI-generated cutlists too.
            if song_asset_id and not cutlist.audio_tracks:
                cutlist.audio_tracks = [AudioTrack(
                    asset_id=song_asset_id,
                    role="music",
                    start_s=0.0,
                    end_s=cutlist.globals.total_duration_s,
                    gain_db=0.0,
                )]
            return cutlist
        except Exception as e:
            logger.warning("AI provider failed, trying next", provider=name, error=str(e))
            continue

    logger.warning("All AI providers exhausted, falling back to programmatic")
    return generate_cutlist_programmatic(
        beat_grid, shot_boundaries, energy_curve, available_shot_types, total_duration,
        style_analysis, style_tier, song_asset_id, user_clip_count,
    )


def generate_cutlist_programmatic(
    beat_grid: BeatGrid,
    shot_boundaries: List[ShotBoundary],
    energy_curve: List[float],
    available_shot_types: List[str],
    total_duration: float = 30.0,
    style_analysis: Optional[Dict[str, Any]] = None,
    style_tier: str = "full_remix",
    song_asset_id: Optional[str] = None,
    user_clip_count: Optional[int] = None,
) -> CutList:
    """Generate a cut-list programmatically without LLM."""
    enable_text = _tier_index(style_tier) >= _tier_index("with_text")
    enable_effects = _tier_index(style_tier) >= _tier_index("with_effects")
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
    previous_slot_end = -1.0
    beat_interval = 60.0 / beat_grid.bpm if beat_grid.bpm else 0.5
    # Aim for roughly one cut every 1-2.5 seconds instead of every single beat.
    min_slot_gap = max(beat_interval * 2, 1.0)

    while beat_idx < len(beats) - 1 and beats[beat_idx] < content_end:
        beat_time = beats[beat_idx]
        next_beat = beats[beat_idx + 1] if beat_idx + 1 < len(beats) else content_end

        section = "intro"
        for seg in segments:
            if seg.start <= beat_time < seg.end:
                section = seg.label
                break

        next_section = "intro"
        for seg in segments:
            if seg.start <= next_beat < seg.end:
                next_section = seg.label
                break

        is_section_boundary = section != next_section

        # Always add section-boundary overlays, even when we skip a slot here.
        if enable_text and is_section_boundary and (not section_change_beats or section_change_beats[-1]["label"] != next_section):
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

        # Skip beats that are too close to the previous cut to avoid tiny slots.
        if beat_time < previous_slot_end + min_slot_gap - 1e-4 and beat_time > 0:
            beat_idx += 1
            continue

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

        duration = max(duration, 1.0)

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
        if enable_effects and detected_transitions and energy > 0.4:
            transition_in = detected_transitions[len(slots) % len(detected_transitions)]

        transition_out = "hard_cut"

        if enable_effects:
            if is_section_boundary and energy > 0.7:
                transition_out = "flash"
            elif is_downbeat and energy > 0.6:
                transition_out = "dissolve"
            elif detected_transitions and transition_out == "hard_cut" and energy > 0.5:
                transition_out = detected_transitions[(len(slots) + 1) % len(detected_transitions)]

        # Determine whether this slot contains a section boundary.
        slot_contains_section_boundary = any(
            beat_time <= seg.start < beat_time + duration
            for seg in segments
        )

        # Build effects for this slot (only when tier allows effects)
        effects = []
        if enable_effects:
            if is_downbeat and energy > 0.7:
                effects.append(
                    Effect(
                        type="zoom_punch_in",
                        start_s=beat_time,
                        duration_s=min(0.3, duration),
                        params=ZoomPunchInParams(
                            target_scale=1.25, duration_ms=250, easing="easeOut"
                        ).model_dump(by_alias=True),
                    )
                )
            if energy < 0.4 and duration > 1.5:
                effects.append(Effect(
                    type="focus_pull",
                    start_s=beat_time + duration * 0.2,
                    duration_s=min(0.8, duration * 0.6),
                    params=FocusPullParams(target_blur=4.0, duration_ms=600, easing="easeInOut").model_dump(by_alias=True),
                ))
            if slot_contains_section_boundary:
                effects.append(Effect(
                    type="film_grain",
                    start_s=beat_time,
                    duration_s=duration,
                    params=FilmGrainParams(intensity=0.15).model_dump(by_alias=True),
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
        previous_slot_end = beat_time + duration

        # Track highest-energy slot for vignette
        if max_energy_slot is None or energy > max_energy_slot.energy_level:
            max_energy_slot = slot

        beat_idx += 1
        if beat_time + duration >= content_end:
            break

    if slots:
        slots[-1].duration_s = max(
            0.5,
            min(slots[-1].duration_s, content_end - slots[-1].start_s),
        )

    # Phase 2: snap slot starts to reference shot boundaries and re-quantize
    # durations so clip boundaries land on musical beats.
    _snap_slots_to_shots_and_beats(
        slots,
        shot_boundaries,
        beat_grid,
        content_end,
        downbeat_lock_radius=settings.beat_snap_downbeat_radius,
        beat_prefer_radius=settings.beat_snap_beat_radius,
    )

    # Cap slot count to prevent over-cutting when the user has few clips.
    # Users can add as many clips as they want; the cap only limits slots per clip.
    if user_clip_count:
        max_slots = max(3, user_clip_count * 3)
        if len(slots) > max_slots:
            slots = slots[:max_slots]

    # Overlays must not extend past the actual rendered content.
    actual_content_end = max(s.start_s + s.duration_s for s in slots) if slots else content_end

    # Add vignette to the highest-energy slot (only when tier allows effects)
    if enable_effects and max_energy_slot is not None:
        max_energy_slot.effects.append(Effect(
            type="vignette",
            start_s=max_energy_slot.start_s,
            duration_s=max_energy_slot.duration_s,
            params=VignetteParams(intensity=0.4).model_dump(by_alias=True),
        ))
        # Re-apply cap in case we pushed it over 2
        if len(max_energy_slot.effects) > 2:
            max_energy_slot.effects = max_energy_slot.effects[:2]

    # Add detected reference overlays (e.g., text/titles from the source video).
    # Hard-coded promotional overlays like "LET'S GO" or "FOLLOW FOR MORE" are
    # intentionally omitted; they are not derived from the reference or user
    # intent and degrade every render. Instead we derive labels from the section
    # names and energy curve already computed for the cutlist.
    if enable_text and slots:
        overlays.append(Overlay(
            text=slots[0].section.upper(),
            start_s=slots[0].start_s,
            end_s=min(actual_content_end, slots[0].start_s + 1.5),
            position="top",
            font="Inter",
            font_size_px=48,
            color="#FFFFFF",
            stroke="#000000",
            animation="fade",
        ))
        # Place the DROP overlay on the real drop section when the structure
        # analysis found one. Otherwise fall back to the highest-energy slot.
        drop_segment = next((seg for seg in segments if seg.label == "drop"), None)
        if drop_segment is not None and drop_segment.start < actual_content_end:
            overlays.append(Overlay(
                text="DROP",
                start_s=drop_segment.start,
                end_s=min(actual_content_end, drop_segment.start + 1.5),
                position="center",
                font="Inter",
                font_size_px=64,
                color="#FF2A6D",
                stroke="#000000",
                animation="fade",
            ))
        elif max_energy_slot is not None and max_energy_slot.energy_level > 0.7:
            overlays.append(Overlay(
                text="DROP",
                start_s=max_energy_slot.start_s,
                end_s=min(actual_content_end, max_energy_slot.start_s + 1.0),
                position="center",
                font="Inter",
                font_size_px=64,
                color="#FF2A6D",
                stroke="#000000",
                animation="fade",
            ))
        overlays.append(Overlay(
            text="OUTRO",
            start_s=max(0.0, actual_content_end - 2.0),
            end_s=actual_content_end,
            position="bottom",
            font="Inter",
            font_size_px=40,
            color="#FFFFFF",
            stroke="#000000",
            animation="fade",
        ))

    for overlay in (detected_overlays if enable_text else []):
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

    # Build audio track for the uploaded song so the render compiler always
    # receives an explicit audio track instead of relying on side-channel config.
    audio_tracks: List[AudioTrack] = []
    if song_asset_id:
        audio_tracks.append(AudioTrack(
            asset_id=song_asset_id,
            role="music",
            start_s=0.0,
            end_s=actual_content_end,
            gain_db=0.0,
            fade_in_s=0.0,
            fade_out_s=0.0,
        ))

    # The rendered output length is determined by the actual slot content, not the
    # requested target. Clamp to the requested cap so we never exceed user intent.
    final_duration_s = min(actual_content_end, total_duration)

    return CutList(
        globals=CutListGlobals(
            total_duration_s=final_duration_s,
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
        audio_tracks=audio_tracks,
    )
