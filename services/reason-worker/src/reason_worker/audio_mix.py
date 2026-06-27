# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
# Commercial SaaS use is prohibited without written permission.
"""Build AudioTrack mix decisions from song structure + dialogue scoring.

Given a cutlist (with real section labels), the song, and the selected user
clips, this module decides:

* how loud the music bed should be in each section (section policy),
* which clips contain dialogue that must be audible (audio scoring),
* the final set of AudioTrack objects (music bed + dialogue tracks) with
  ducking parameters so the render compiler can sidechain-duck the music.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, List, Optional

from shared_py.models import AudioTrack, BeatGrid, BeatSegment, CutList
from shared_py.logging_config import StructuredLogger

from reason_worker.audio_scoring import (
    DialogueSegment,
    ScoringConfig,
    score_clip_dialogue,
)

logger = StructuredLogger("reason_worker.audio_mix")


@dataclass
class SectionPolicy:
    """Mix policy for a named song section."""

    music_gain_db: float = 0.0
    duck_gain_db: float = -12.0  # how much music drops when dialogue is present
    duck_attack_ms: float = 20.0
    duck_release_ms: float = 250.0
    duck_threshold: float = 0.15
    # If True, the music bed is never ducked in this section (e.g. drop).
    music_full: bool = False
    # Fade music in/out at section boundaries (seconds).
    fade_in_s: float = 0.0
    fade_out_s: float = 0.0


DEFAULT_POLICIES: Dict[str, SectionPolicy] = {
    "intro": SectionPolicy(
        music_gain_db=-4.0,
        duck_gain_db=-10.0,
        fade_in_s=1.0,
    ),
    "verse": SectionPolicy(
        music_gain_db=-2.0,
        duck_gain_db=-14.0,
    ),
    "chorus": SectionPolicy(
        music_gain_db=0.0,
        duck_gain_db=-10.0,
    ),
    "drop": SectionPolicy(
        music_gain_db=0.0,
        music_full=True,
        duck_gain_db=-6.0,  # kept for safety, ignored when music_full=True
    ),
    "bridge": SectionPolicy(
        music_gain_db=-2.0,
        duck_gain_db=-12.0,
    ),
    "outro": SectionPolicy(
        music_gain_db=-4.0,
        duck_gain_db=-8.0,
        fade_out_s=2.0,
    ),
}


def _section_at(time_s: float, segments: List[BeatSegment]) -> str:
    """Return the section label active at ``time_s``."""
    for seg in segments:
        if seg.start <= time_s < seg.end:
            return seg.label
    if segments and time_s >= segments[-1].end:
        return segments[-1].label
    return "verse"


def _policy_for(section: str) -> SectionPolicy:
    return DEFAULT_POLICIES.get(section, DEFAULT_POLICIES["verse"])


def _dialogue_segments_for_slot(
    slot,
    clip_path: str,
    cfg: ScoringConfig,
) -> List[DialogueSegment]:
    """Find dialogue segments inside the selected window of a clip."""
    # When no source window has been chosen, start from the beginning of the
    # clip so early dialogue is not missed.
    window_start = slot.source_window_start_s if slot.source_window_start_s is not None else 0.0
    window_end = window_start + slot.duration_s

    segments = score_clip_dialogue(clip_path, cfg=cfg)

    # Translate clip-relative dialogue times to cutlist (reference) time.
    shifted: List[DialogueSegment] = []
    for seg in segments:
        if seg.total_score < cfg.min_dialogue_score:
            continue
        seg_start = seg.start_s
        seg_end = seg.end_s
        # Keep only the part that overlaps the chosen window.
        if seg_end <= window_start or seg_start >= window_end:
            continue
        start_in_window = max(0.0, seg_start - window_start)
        end_in_window = min(slot.duration_s, seg_end - window_start)
        if end_in_window <= start_in_window + 0.1:
            continue
        shifted.append(
            DialogueSegment(
                start_s=start_in_window,
                end_s=end_in_window,
                text=seg.text,
                speech_score=seg.speech_score,
                phrase_match_score=seg.phrase_match_score,
                source_clip_id=slot.selected_clip_id,
            )
        )
    return shifted


def _split_music_by_sections(
    total_duration: float,
    song_asset_id: str,
    segments: List[BeatSegment],
    base_policy: SectionPolicy,
) -> List[AudioTrack]:
    """Split the music bed into per-section tracks so ducking can be disabled in drops."""
    if not segments:
        return [
            AudioTrack(
                asset_id=song_asset_id,
                role="music",
                start_s=0.0,
                end_s=total_duration,
                gain_db=base_policy.music_gain_db,
                fade_in_s=base_policy.fade_in_s,
                fade_out_s=base_policy.fade_out_s,
                duck_gain_db=base_policy.duck_gain_db,
                duck_attack_ms=base_policy.duck_attack_ms,
                duck_release_ms=base_policy.duck_release_ms,
                duck_threshold=base_policy.duck_threshold,
                duck_disabled=False,
            )
        ]

    tracks: List[AudioTrack] = []
    for seg in segments:
        if seg.end <= 0 or seg.start >= total_duration:
            continue
        policy = _policy_for(seg.label)
        start = max(0.0, seg.start)
        end = min(total_duration, seg.end)
        # Small cross-fade boundaries between sections handled by the duck release.
        tracks.append(
            AudioTrack(
                asset_id=song_asset_id,
                role="music",
                start_s=start,
                end_s=end,
                gain_db=policy.music_gain_db,
                fade_in_s=0.2 if start > 0 else policy.fade_in_s,
                fade_out_s=0.2 if end < total_duration else policy.fade_out_s,
                duck_gain_db=policy.duck_gain_db,
                duck_attack_ms=policy.duck_attack_ms,
                duck_release_ms=policy.duck_release_ms,
                duck_threshold=policy.duck_threshold,
                duck_disabled=policy.music_full,
            )
        )
    return tracks


def build_audio_tracks(
    cutlist: CutList,
    beat_grid: Optional[BeatGrid] = None,
    song_asset_id: Optional[str] = None,
    clip_paths: Optional[Dict[str, str]] = None,
    scoring_cfg: Optional[ScoringConfig] = None,
    max_dialogue_tracks: int = 50,
) -> List[AudioTrack]:
    """Build the final music + dialogue AudioTrack list for ``cutlist``.

    The music bed is split into per-section tracks so sections like the drop can
    keep full music level, while verse/chorus tracks are sidechain-ducked under
    dialogue. Dialogue tracks carry source offsets so the renderer extracts only
    the relevant clip window and places it at the correct timeline position.

    The number of dialogue tracks is capped to keep the final FFmpeg command
    line within Windows' length limit; only the highest-scoring segments are kept.
    """
    clip_paths = clip_paths or {}
    scoring_cfg = scoring_cfg or ScoringConfig()
    total_duration = cutlist.globals.total_duration_s

    segments = beat_grid.segments if beat_grid else []

    # Section policies active in this cutlist.
    active_sections = {seg.label for seg in segments} or {"verse"}

    # Pick the most aggressive ducking policy among active sections for safety.
    policies = [_policy_for(s) for s in active_sections]
    music_policy = min(
        policies,
        key=lambda p: (p.duck_gain_db, -p.duck_attack_ms),
    )

    tracks: List[AudioTrack] = []
    if song_asset_id:
        tracks.extend(
            _split_music_by_sections(
                total_duration, song_asset_id, segments, music_policy
            )
        )

    # Gather dialogue tracks from selected clips.
    dialogue_tracks: List[AudioTrack] = []
    for slot in cutlist.slots:
        clip_id = slot.selected_clip_id
        if not clip_id or clip_id not in clip_paths:
            continue
        window_start = (
            slot.source_window_start_s
            if slot.source_window_start_s is not None
            else 0.0
        )
        segs = _dialogue_segments_for_slot(slot, clip_paths[clip_id], scoring_cfg)
        if not segs:
            continue
        # Keep only the strongest segment per slot to avoid flooding the mixer
        # with low-confidence detections.
        segs = sorted(segs, key=lambda s: s.total_score, reverse=True)[:1]
        for seg in segs:
            # Translate from slot-relative to global cutlist time.
            global_start = slot.start_s + seg.start_s
            global_end = slot.start_s + seg.end_s
            # Clamp to total duration.
            global_start = min(global_start, total_duration)
            global_end = min(global_end, total_duration)
            if global_end <= global_start + 0.1:
                continue

            section = _section_at(global_start, segments)
            policy = _policy_for(section)
            # Iconic lines get a small extra gain boost.
            gain_db = -2.0 if seg.phrase_match_score > 0.8 else -4.0

            # Source offset inside the original clip.
            source_start = window_start + seg.start_s
            source_end = window_start + seg.end_s

            dialogue_tracks.append(
                AudioTrack(
                    asset_id=clip_id,
                    role="dialogue",
                    start_s=global_start,
                    end_s=global_end,
                    gain_db=gain_db,
                    duck_gain_db=policy.duck_gain_db if not policy.music_full else -6.0,
                    duck_attack_ms=policy.duck_attack_ms,
                    duck_release_ms=policy.duck_release_ms,
                    duck_threshold=policy.duck_threshold,
                    source_start_s=source_start,
                    source_end_s=source_end,
                    slot_index=slot.index,
                )
            )

    # Keep only the highest-scoring dialogue tracks so the final FFmpeg command
    # stays within Windows' command-line length limit.
    dialogue_tracks.sort(key=lambda t: t.start_s)
    dialogue_tracks.sort(key=lambda t: t.gain_db, reverse=True)
    dialogue_tracks = dialogue_tracks[:max_dialogue_tracks]

    # Merge overlapping dialogue tracks from the same clip to avoid redundant inputs.
    # Simple greedy merge, but keep the merged source window covering the union.
    merged: List[AudioTrack] = []
    for track in sorted(dialogue_tracks, key=lambda t: (t.asset_id, t.start_s)):
        if (
            merged
            and merged[-1].asset_id == track.asset_id
            and merged[-1].end_s >= track.start_s - 0.1
        ):
            merged[-1].end_s = max(merged[-1].end_s, track.end_s)
            merged[-1].gain_db = max(merged[-1].gain_db, track.gain_db)
            if track.source_start_s is not None and merged[-1].source_start_s is not None:
                merged[-1].source_start_s = min(merged[-1].source_start_s, track.source_start_s)
                merged[-1].source_end_s = max(merged[-1].source_end_s, track.source_end_s or track.end_s)
        else:
            merged.append(track)

    tracks.extend(merged)
    return tracks
