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
    CutList, CutListGlobals, Slot, Overlay, Effect, BeatGrid, BeatSegment, ShotBoundary, SectionMarker, AudioTrack,
    ZoomPunchInParams, FocusPullParams, FilmGrainParams, VignetteParams,
    BehaviorVector, AdaptiveFeatures, MusicEventGrid,
)
from reason_worker.kinetic_compose import assign_kinetic_text_to_slots
from reason_worker.speed_ramps import assign_speed_ramps_to_slots
from reason_worker.slot_generator import generate_slots_adaptive
from reason_worker.narrative_arcs import select_arc
from reason_worker.arc_anchor import map_arc_to_song, anchor_for_time

# Maximum contiguous slot length.  Trailer-style / AMV edits need longer holds
# (5-8s) than the old 4.0s beat-slot cap; otherwise adaptive-density cuts leave
# freeze-frame gaps between slots.
SLOT_DURATION_MAX_S = 8.0


def _section_at_time(time_s: float, segments: List[BeatSegment]) -> str:
    """Return the section label active at ``time_s``."""
    for seg in segments:
        if seg.start <= time_s < seg.end:
            return seg.label
    if segments and time_s >= segments[-1].end:
        return segments[-1].label
    return "verse"


def _energy_at_time(time_s: float, energy_curve: List[float], content_end: float) -> float:
    """Sample the energy curve at ``time_s``."""
    if not energy_curve or content_end <= 0:
        return 0.5
    progress = time_s / content_end
    energy_idx = min(int(progress * len(energy_curve)), len(energy_curve) - 1)
    return energy_curve[energy_idx]


def _apply_slot_style(
    slot: Slot,
    beat_grid: BeatGrid,
    segments: List[BeatSegment],
    downbeats: set,
    shot_pool: List[str],
    energy_curve: List[float],
    style_analysis: Dict[str, Any],
    enable_effects: bool,
    enable_text: bool,
    state: Dict[str, Any],
) -> None:
    """Fill transitions, effects, shot type, and motion hints for a slot skeleton.

    Mutates ``slot`` in place and updates ``state`` (shot_rotation, slot_count,
    section_change_beats, max_energy_slot).
    """
    beat_time = slot.start_s
    duration = slot.duration_s
    content_end = state["content_end"]

    section = _section_at_time(beat_time, segments)
    next_section = _section_at_time(beat_time + duration, segments)
    is_section_boundary = section != next_section

    section_change_beats = state.get("section_change_beats", [])
    if is_section_boundary and (
        not section_change_beats or section_change_beats[-1]["label"] != next_section
    ):
        section_change_beats.append({"label": next_section.upper(), "start_s": beat_time + duration})
    state["section_change_beats"] = section_change_beats

    energy = _energy_at_time(beat_time, energy_curve, content_end)
    is_downbeat = round(beat_time, 2) in downbeats

    shot_rotation = state.get("shot_rotation", 0)
    if energy < 0.3:
        target = "wide" if "wide" in shot_pool else shot_pool[0]
    elif energy < 0.6:
        target = "medium" if "medium" in shot_pool else shot_pool[shot_rotation % len(shot_pool)]
        shot_rotation += 1
    elif energy < 0.8:
        target = (
            "medium_close_up"
            if "medium_close_up" in shot_pool
            else "close_up" if "close_up" in shot_pool else shot_pool[-1]
        )
        shot_rotation += 1
    else:
        target = "close_up" if "close_up" in shot_pool else shot_pool[-1]
        shot_rotation += 1
    state["shot_rotation"] = shot_rotation

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

    slot_count = state.get("slot_count", 0)

    transition_in = "hard_cut"
    if enable_effects and detected_transitions and energy > 0.4:
        transition_in = detected_transitions[slot_count % len(detected_transitions)]

    transition_out = "hard_cut"
    if enable_effects:
        if is_section_boundary and energy > 0.7:
            transition_out = "flash"
        elif is_downbeat and energy > 0.6:
            transition_out = "dissolve"
        elif detected_transitions and transition_out == "hard_cut" and energy > 0.5:
            transition_out = detected_transitions[(slot_count + 1) % len(detected_transitions)]

    slot_contains_section_boundary = any(
        beat_time <= seg.start < beat_time + duration for seg in segments
    )

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
            effects.append(
                Effect(
                    type="focus_pull",
                    start_s=beat_time + duration * 0.2,
                    duration_s=min(0.8, duration * 0.6),
                    params=FocusPullParams(target_blur=4.0, duration_ms=600, easing="easeInOut").model_dump(by_alias=True),
                )
            )
        if slot_contains_section_boundary:
            effects.append(
                Effect(
                    type="film_grain",
                    start_s=beat_time,
                    duration_s=duration,
                    params=FilmGrainParams(intensity=0.15).model_dump(by_alias=True),
                )
            )

    if camera_motions:
        motion_hint = camera_motions[slot_count % len(camera_motions)]
    else:
        motion_hint = "static" if energy < 0.3 else "handheld" if energy > 0.8 else "gimbal"

    slot.section = section
    slot.transition_in = transition_in
    slot.transition_out = transition_out
    slot.target_shot_type = target
    slot.subject_hint = f"{section} section, energy {energy:.1f}"
    slot.motion_hint = motion_hint
    slot.energy_level = energy
    slot.effects = effects[:2]

    # Phase 2: annotate slot with narrative arc beat when emotion-led cuts are on.
    arc_anchors = state.get("arc_anchors")
    if arc_anchors:
        anchor = anchor_for_time(arc_anchors, beat_time)
        if anchor is not None:
            slot.story_beat = anchor.name
            slot.arc_beat_emotion_target = anchor.emotion_target
            slot.arc_beat_preferred_shots = anchor.preferred_shots
            slot.energy_level = anchor.energy_target
            slot.subject_hint = f"{anchor.name}: {anchor.text_archetype}"
            if anchor.preferred_shots:
                # Prefer the arc's shot request, but keep it in the available pool.
                pool = [s for s in shot_pool if s in anchor.preferred_shots]
                if pool:
                    slot.target_shot_type = pool[state["shot_rotation"] % len(pool)]
                    state["shot_rotation"] = state.get("shot_rotation", 0) + 1

    max_energy_slot = state.get("max_energy_slot")
    if max_energy_slot is None or energy > max_energy_slot.energy_level:
        state["max_energy_slot"] = slot

    state["slot_count"] = slot_count + 1

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
    music_event_grid: Optional[MusicEventGrid] = None,
    event_snap_radius: float = 0.08,
) -> None:
    """Snap slot starts to shot boundaries and ensure slots do not overlap or exceed content.

    Uses tiered importance:
    - Music events (kick/snare/bass-drop) within ``event_snap_radius`` take top priority
      when a grid is provided.
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
        # Tiered snap: music event > downbeat > beat > shot.
        event = None
        if music_event_grid is not None:
            events = music_event_grid.events_in_window(slot.start_s, event_snap_radius)
            if events:
                event = events[0]

        nearest_downbeat_dist = min((abs(slot.start_s - d) for d in downbeats), default=float("inf"))
        nearest_beat_dist = min((abs(slot.start_s - b) for b in beats), default=float("inf"))
        nearest_downbeat = min(downbeats, key=lambda d: abs(d - slot.start_s)) if downbeats else None
        nearest_beat = min(beats, key=lambda b: abs(b - slot.start_s)) if beats else None

        if event is not None and abs(event.time_s - slot.start_s) <= event_snap_radius:
            new_start = event.time_s
        elif nearest_downbeat is not None and nearest_downbeat_dist < downbeat_lock_radius:
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
        # than SLOT_DURATION_MAX_S. We no longer truncate at reference shot
        # boundaries because that produces too many tiny slots when beats and
        # shots interleave.
        available = max_end - slot.start_s
        prev_end = (
            slots[i - 1].start_s + slots[i - 1].duration_s
            if i > 0
            else 0.0
        )
        if available <= 1e-4:
            # Slot has no room; give it a minimal beat-long window if possible.
            slot.duration_s = round(min(beat_interval, content_end - slot.start_s), 3)
        else:
            if available <= SLOT_DURATION_MAX_S:
                # Contiguous region fits inside the cap; just fill it.
                duration = available
            else:
                # The gap to the next slot is larger than the cap. Try to hold
                # the last SLOT_DURATION_MAX_S seconds so the slot ends exactly
                # on the next cut. If that would leave a large empty gap before
                # this slot, fill the whole gap forward instead — a long clip is
                # better than a freeze-frame.
                shifted_start = next_start - SLOT_DURATION_MAX_S
                if shifted_start >= prev_end + 1e-3:
                    preceding_gap = shifted_start - prev_end
                    if preceding_gap <= 0.5:
                        slot.start_s = round(shifted_start, 3)
                        duration = SLOT_DURATION_MAX_S
                    else:
                        duration = available
                else:
                    duration = available
            duration = max(beat_interval, duration)
            slot.duration_s = round(min(duration, available), 3)

        # Keep effects inside the adjusted slot bounds.
        for effect in slot.effects:
            if effect.start_s < slot.start_s:
                effect.start_s = slot.start_s
            max_dur = max(0.0, slot.start_s + slot.duration_s - effect.start_s)
            effect.duration_s = max(0.0, min(effect.duration_s, max_dur))

    # Final contiguity pass: extend each slot so it touches the next slot's
    # start. Small rounding / cap-shift gaps would otherwise fail the
    # max_slot_gap gate in the Golden Render Suite.
    slots.sort(key=lambda s: s.start_s)
    for i, slot in enumerate(slots):
        next_start = slots[i + 1].start_s if i + 1 < len(slots) else content_end
        if next_start > slot.start_s:
            slot.duration_s = round(next_start - slot.start_s, 3)

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


def _behavior_from_style_analysis(
    style_analysis: Dict[str, Any],
    total_duration: float = 30.0,
) -> BehaviorVector:
    """Derive an initial behavior vector from a reference style genome.

    T.8.13: User/LLM overrides (``requested_cut_density_per_min`` or
    ``requested_slot_count``) take precedence over reference-derived density,
    so the edit is not slaved to the duration of the inspiration clip.
    """
    families = style_analysis.get("families") or {}
    cut_rhythm = families.get("cut_rhythm") or families.get("cutRhythm") or {}
    density_per_min = cut_rhythm.get("cut_density_per_min") or cut_rhythm.get("cutDensityPerMin")

    # T.8.13: explicit user / LLM pacing requests.
    requested_density_per_min = (
        cut_rhythm.get("requested_cut_density_per_min")
        or cut_rhythm.get("requestedCutDensityPerMin")
    )
    requested_slot_count = (
        style_analysis.get("requested_slot_count")
        or style_analysis.get("requestedSlotCount")
    )

    reference_present = bool(style_analysis)

    if requested_density_per_min is not None:
        cut_density_per_sec = max(0.01, min(2.0, float(requested_density_per_min) / 60.0))
    elif requested_slot_count is not None and total_duration > 0:
        cut_density_per_sec = max(0.01, min(2.0, float(requested_slot_count) / total_duration))
    elif density_per_min:
        cut_density_per_sec = max(0.01, min(2.0, density_per_min / 60.0))
    else:
        # Fallback for music-video-like content. This is the Phase 1 scaffold;
        # later phases replace it with KNN / MLP prediction.
        cut_density_per_sec = 0.16

    # Derive mean slot duration from density, capped to reasonable bounds.
    slot_duration_mean_s = max(0.5, min(8.0, 1.0 / max(cut_density_per_sec, 0.01)))

    # Phase 1 audio policy heuristic: reference-driven AMV/MV-style edits keep
    # the song dominant and only surface iconic quotes. Speech-forward edits
    # (no reference or low cut density) keep most dialogue and push the song back.
    if reference_present and cut_density_per_sec > 0.12:
        # Music video / AMV cluster
        audio_strategy = "iconic_only"
        # 0.85 was too high for AMV fragments; 0.55 lets lyric/keyword matches
        # through while still filtering out weak whisper noise.
        min_importance = 0.55
        sfx_mute = 0.9
        song_mode = "dominant"
        duck = 0.5
    else:
        # Informative / podcast / vlog cluster
        audio_strategy = "speech_only"
        min_importance = 0.3
        sfx_mute = 0.95
        song_mode = "ambient"
        duck = 0.9

    return BehaviorVector(
        cut_density_per_sec=cut_density_per_sec,
        slot_duration_mean_s=slot_duration_mean_s,
        slot_duration_std_s=min(slot_duration_mean_s * 0.3, 2.0),
        clip_audio_inclusion_strategy=audio_strategy,
        clip_audio_min_importance=min_importance,
        sfx_mute_aggressiveness=sfx_mute,
        song_background_mode=song_mode,
        duck_aggressiveness=duck,
    )


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
    behavior: Optional[BehaviorVector] = None,
    features: Optional[AdaptiveFeatures] = None,
    music_event_grid: Optional[MusicEventGrid] = None,
) -> CutList:
    """Generate a cut-list using the configured AI provider chain.

    Supports comma-separated fallback chain via AI_PROVIDER env var:
        AI_PROVIDER=kimi,qwen,programmatic
    Programmatic is always the final fallback if the chain exhausts.
    """
    provider_chain = os.environ.get("AI_PROVIDER", "programmatic")
    names = [n.strip() for n in provider_chain.split(",") if n.strip()]

    behavior = behavior or _behavior_from_style_analysis(style_analysis or {}, total_duration=total_duration)
    features = features or AdaptiveFeatures()

    for name in names:
        if name == "programmatic":
            return generate_cutlist_programmatic(
                beat_grid, shot_boundaries, energy_curve, available_shot_types, total_duration,
                style_analysis, style_tier, song_asset_id, user_clip_count,
                behavior=behavior,
                features=features,
                music_event_grid=music_event_grid,
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
        behavior=behavior,
        features=features,
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
    behavior: Optional[BehaviorVector] = None,
    features: Optional[AdaptiveFeatures] = None,
    music_event_grid: Optional[MusicEventGrid] = None,
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

    # The cutlist should span the requested duration (typically the song length).
    # Do NOT clamp to reference shot boundaries or energy curve end — user clips
    # provide the actual visual content and the reference only drives timing/style.
    content_end = float(total_duration)

    beats = [b for b in beat_grid.beats if b <= content_end]
    downbeats = set(round(b, 2) for b in beat_grid.downbeats)
    segments = beat_grid.segments

    shot_pool = available_shot_types if available_shot_types else ["wide", "medium", "close_up"]

    behavior = behavior or _behavior_from_style_analysis(style_analysis, total_duration=total_duration)
    features = features or AdaptiveFeatures()

    slots = []
    overlays = []
    state: Dict[str, Any] = {
        "content_end": content_end,
        "shot_rotation": 0,
        "slot_count": 0,
        "section_change_beats": [],
        "max_energy_slot": None,
    }

    # Phase 2: when emotion-led cuts are enabled, select a narrative arc and map
    # its beats to concrete song time windows using energy valleys/peaks.
    if features.use_emotion_led_cuts:
        arc_template = select_arc(energy_curve, style_analysis, key=None)
        arc_anchors = map_arc_to_song(arc_template, energy_curve, beat_grid, content_end)
        state["arc_template"] = arc_template
        state["arc_anchors"] = arc_anchors
        logger.info(
            "Selected arc",
            arc=arc_template.name,
            anchors=[{"name": a.name, "start": a.start_s, "end": a.end_s} for a in arc_anchors],
        )

    if features.use_adaptive_slot_density:
        # Density-driven slot generation: choose cut positions from beat candidates
        # instead of emitting one slot per beat. This prevents the forced clip repeats
        # that occur when slot_count exceeds clip_count.
        slot_skeletons = generate_slots_adaptive(
            beat_grid,
            total_duration,
            behavior,
            energy_curve,
            content_end,
            music_event_grid=music_event_grid,
        )
        for slot in slot_skeletons:
            _apply_slot_style(
                slot,
                beat_grid,
                segments,
                downbeats,
                shot_pool,
                energy_curve,
                style_analysis,
                enable_effects,
                enable_text,
                state,
            )
            slots.append(slot)
    else:
        # Legacy beat-counting loop. Preserved for safety and A/B rollback.
        beat_idx = 0
        last_cut_was_downbeat = False
        previous_slot_end = -1.0
        beat_interval = 60.0 / beat_grid.bpm if beat_grid.bpm else 0.5
        # Aim for roughly one cut every 1-2.5 seconds instead of every single beat.
        min_slot_gap = max(beat_interval * 2, 1.0)

        while beat_idx < len(beats) - 1 and beats[beat_idx] < content_end:
            beat_time = beats[beat_idx]
            next_beat = beats[beat_idx + 1] if beat_idx + 1 < len(beats) else content_end

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

            slot = Slot(
                index=len(slots),
                start_s=beat_time,
                duration_s=duration,
                beat_index=beat_idx,
                section=_section_at_time(beat_time, segments),
                transition_in="hard_cut",
                transition_out="hard_cut",
                target_shot_type="medium",
                subject_hint="",
                motion_hint="static",
                energy_level=energy,
                required_tags=[],
                avoid_tags=[],
                effects=[],
            )
            _apply_slot_style(
                slot,
                beat_grid,
                segments,
                downbeats,
                shot_pool,
                energy_curve,
                style_analysis,
                enable_effects,
                enable_text,
                state,
            )
            slots.append(slot)
            previous_slot_end = beat_time + duration

            beat_idx += 1
            if beat_time + duration >= content_end:
                break

    section_change_beats = state.get("section_change_beats", [])
    max_energy_slot = state.get("max_energy_slot")

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
        music_event_grid=music_event_grid,
        event_snap_radius=settings.beat_snap_event_radius,
    )

    # Cap slot count to prevent over-cutting when the user has few clips.
    # Users can add as many clips as they want; the cap only limits slots per clip.
    if user_clip_count:
        max_slots = max(3, user_clip_count * 3)
        if len(slots) > max_slots:
            slots = slots[:max_slots]

    # Assign cinematic kinetic text to high-energy / peak narrative slots.
    # This replaces the old lyric-overlay stub with LLM-composed or word-bank
    # phrases that actually match the edit's mood.
    source_ip_hint = style_analysis.get("source_ip_hint") if isinstance(style_analysis, dict) else None
    if enable_text:
        # Re-enable LLM composition by default. Override with KINETIC_TEXT_LLM=0
        # only for explicit debugging of the deterministic fallback path.
        import os
        use_llm = os.environ.get("KINETIC_TEXT_LLM", "1").lower() not in ("0", "false", "off")
        assign_kinetic_text_to_slots(
            slots,
            source_ip_hint=source_ip_hint,
            use_llm=use_llm,
            max_text_count=max(3, int(0.1 * len(slots))),
        )
        for slot in slots:
            if slot.enable_kinetic_text:
                slot.text_z_layer = "behind_subject"

    # Assign speed ramps to high-energy / transition slots (Sprint A real path).
    if enable_effects:
        assign_speed_ramps_to_slots(slots, min_ramps=2, max_ramps=6)

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
    # Hard-coded section labels (INTRO, DROP, OUTRO, etc.) are intentionally
    # omitted — they read as ugly subtitles and degrade the viewing experience.
    # Only overlays actually detected in the reference video are preserved.
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
