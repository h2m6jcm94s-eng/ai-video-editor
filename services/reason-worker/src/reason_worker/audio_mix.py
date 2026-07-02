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
from typing import Any, Dict, List, Optional

from shared_py.models import AudioTrack, BeatGrid, BeatSegment, CutList, BehaviorVector, SongMeaning, AdaptiveFeatures
from shared_py.feature_tracer import FeatureTracer
from shared_py.logging_config import StructuredLogger

from reason_worker.audio_scoring import (
    DialogueSegment,
    ScoringConfig,
    WordTimestamp,
    score_clip_dialogue,
)
from reason_worker.captions import generate_caption_overlays_from_segments
from reason_worker.clip_audio_filter import (
    AudioSegment as ClipAudioSegment,
    filter_clip_audio_for_inclusion,
)
from reason_worker.iconic_quotes import (
    TranscriptSegment,
    detect_iconic_quotes,
)
from reason_worker.narrative_mode import determine_narrative_mode

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

# Compressor profiles keyed by narrative mode. These values are carried on the
# AudioTrack so the render compiler can adapt sidechaincompress parameters.
DUCK_PROFILES: Dict[str, Dict[str, Any]] = {
    "music_video": {
        "threshold": 0.10,
        "ratio": 6,
        "attack_ms": 30,
        "release_ms": 250,
        "duck_gain_db": -10,
    },
    "vlog": {
        "threshold": 0.12,
        "ratio": 4,
        "attack_ms": 80,
        "release_ms": 400,
        "duck_gain_db": -8,
    },
    "podcast": {
        "threshold": 0.05,
        "ratio": 8,
        "attack_ms": 10,
        "release_ms": 200,
        "duck_gain_db": -14,
    },
    "informative": {
        "threshold": 0.08,
        "ratio": 6,
        "attack_ms": 30,
        "release_ms": 300,
        "duck_gain_db": -12,
    },
    "default": {
        "threshold": 0.12,
        "ratio": 4,
        "attack_ms": 150,
        "release_ms": 350,
        "duck_gain_db": -8,
    },
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


def _duck_profile_for(
    narrative_mode: str,
    content_signals: Optional[dict],
) -> Dict[str, Any]:
    """Pick a ducking compressor profile from content type, falling back to default."""
    if narrative_mode in DUCK_PROFILES:
        return DUCK_PROFILES[narrative_mode]
    if content_signals:
        speech_ratio = float(content_signals.get("speech_ratio", 0.0) or 0.0)
        song_present = bool(content_signals.get("song_present", False))
        if song_present and speech_ratio >= 0.5:
            return DUCK_PROFILES["podcast"]
        if song_present and speech_ratio >= 0.2:
            return DUCK_PROFILES["informative"]
        if song_present and speech_ratio > 0.0:
            return DUCK_PROFILES["vlog"]
    return DUCK_PROFILES["default"]


def should_duck_audio(
    has_song: bool,
    has_dialogue: bool,
    behavior: BehaviorVector,
) -> tuple[bool, str]:
    """
    Deterministic gate. Audio ducking is a safety feature — when in doubt, ENABLE it.
    Returns (enabled, reason).
    """
    if not has_song:
        return False, "no_song_present"
    if not has_dialogue:
        return False, "no_dialogue_detected"
    if getattr(behavior, "song_dominance", 0.0) >= 0.95:
        # User explicitly wants music-dominant (e.g. pure MV with no dialogue surfacing)
        return False, "song_dominance_user_preference"
    return True, "song_plus_dialogue_detected"


def _dialogue_segments_for_slot(
    slot,
    clip_path: str,
    cfg: ScoringConfig,
    behavior: BehaviorVector,
    source_ip_hint: Optional[str] = None,
    content_embedding: Optional[dict] = None,
) -> List[DialogueSegment]:
    """Find dialogue segments inside the selected window of a clip.

    Applies the behavior-vector audio policy so only segments that match the
    project's inclusion strategy survive into the final mix.
    """
    # When no source window has been chosen, start from the beginning of the
    # clip so early dialogue is not missed.
    window_start = slot.source_window_start_s if slot.source_window_start_s is not None else 0.0
    window_end = window_start + slot.duration_s

    segments = score_clip_dialogue(clip_path, cfg=cfg)
    if not segments:
        return []

    # Score iconic-quote potential and convert to the generic audio-segment model.
    transcript_segments = [
        TranscriptSegment(start_s=seg.start_s, end_s=seg.end_s, text=seg.text or "")
        for seg in segments
    ]
    iconic_quotes = {
        (round(q.segment.start_s, 3), round(q.segment.end_s, 3), q.segment.text.strip()): q
        for q in detect_iconic_quotes(
            transcript_segments,
            source_ip_hint=source_ip_hint,
            clip_path=clip_path,
            max_llm_candidates=20,
            content_embedding=content_embedding,
        )
    }

    candidates: List[ClipAudioSegment] = []
    for seg in segments:
        key = (round(seg.start_s, 3), round(seg.end_s, 3), (seg.text or "").strip())
        iconic = iconic_quotes.get(key)
        candidates.append(
            ClipAudioSegment(
                start_s=seg.start_s,
                end_s=seg.end_s,
                text=seg.text or None,
                is_speech=True,
                importance=seg.total_score,
                # Use the LLM/heuristic iconic score only. The regex-based
                # phrase_match_score is 0 whenever cfg.iconic_phrases is empty,
                # which silently disables the iconic dialogue boost (B3).
                iconic_score=(iconic.importance if iconic else 0.0),
                source_clip_id=slot.selected_clip_id,
                words=seg.words,
            )
        )
    survivors = filter_clip_audio_for_inclusion(candidates, behavior)

    # Translate clip-relative dialogue times to cutlist (reference) time.
    shifted: List[DialogueSegment] = []
    for seg in survivors:
        if seg.importance < cfg.min_dialogue_score:
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
        # Preserve word-level timestamps so caption burning (AC1) can use them.
        shifted_words = []
        for word in (seg.words or []):
            if word.end_s <= window_start or word.start_s >= window_end:
                continue
            shifted_words.append(
                WordTimestamp(
                    text=word.text,
                    start_s=max(0.0, word.start_s - window_start),
                    end_s=min(slot.duration_s, word.end_s - window_start),
                )
            )
        shifted.append(
            DialogueSegment(
                start_s=start_in_window,
                end_s=end_in_window,
                text=seg.text or "",
                speech_score=seg.importance,
                phrase_match_score=seg.iconic_score,
                source_clip_id=slot.selected_clip_id,
                words=shifted_words,
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
    behavior: Optional[BehaviorVector] = None,
    source_ip_hint: Optional[str] = None,
    content_embedding: Optional[dict] = None,
    song_meaning: Optional[SongMeaning] = None,
    features: Optional[AdaptiveFeatures] = None,
) -> List[AudioTrack]:
    """Build the final music + dialogue AudioTrack list for ``cutlist``.

    The music bed is split into per-section tracks so sections like the drop can
    keep full music level, while verse/chorus tracks are sidechain-ducked under
    dialogue. Dialogue tracks carry source offsets so the renderer extracts only
    the relevant clip window and places it at the correct timeline position.

    The number of dialogue tracks is capped to keep the final FFmpeg command
    line within Windows' length limit; only the highest-scoring segments are kept.
    """
    with FeatureTracer("dialogue", gated_in=True) as ft:
        return _build_audio_tracks(
            cutlist,
            beat_grid,
            song_asset_id,
            clip_paths,
            scoring_cfg,
            max_dialogue_tracks,
            behavior,
            source_ip_hint,
            content_embedding,
            song_meaning,
            features,
            ft,
        )


def _build_audio_tracks(
    cutlist: CutList,
    beat_grid: Optional[BeatGrid] = None,
    song_asset_id: Optional[str] = None,
    clip_paths: Optional[Dict[str, str]] = None,
    scoring_cfg: Optional[ScoringConfig] = None,
    max_dialogue_tracks: int = 50,
    behavior: Optional[BehaviorVector] = None,
    source_ip_hint: Optional[str] = None,
    content_embedding: Optional[dict] = None,
    song_meaning: Optional[SongMeaning] = None,
    features: Optional[AdaptiveFeatures] = None,
    ft: Optional[FeatureTracer] = None,
) -> List[AudioTrack]:
    clip_paths = clip_paths or {}
    scoring_cfg = scoring_cfg or ScoringConfig()
    behavior = behavior or BehaviorVector()
    features = features or AdaptiveFeatures()
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

    # Build music bed first.
    tracks: List[AudioTrack] = []
    if song_asset_id:
        tracks.extend(
            _split_music_by_sections(
                total_duration, song_asset_id, segments, music_policy
            )
        )

    # Gather dialogue tracks from selected clips BEFORE deciding ducking so the
    # gate is based on actual detected dialogue, not a pre-computed embedding.
    dialogue_tracks: List[AudioTrack] = []
    slot_dialogue_segments: List[tuple[int, str, float, float, List[DialogueSegment]]] = []
    for slot in cutlist.slots:
        clip_id = slot.selected_clip_id
        if not clip_id or clip_id not in clip_paths:
            continue
        window_start = (
            slot.source_window_start_s
            if slot.source_window_start_s is not None
            else 0.0
        )
        segs = _dialogue_segments_for_slot(slot, clip_paths[clip_id], scoring_cfg, behavior, source_ip_hint=source_ip_hint, content_embedding=content_embedding)
        if segs:
            slot_dialogue_segments.append((slot.index, clip_id, window_start, slot.start_s, segs))
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
            # Iconic lines get a small extra gain boost. Threshold aligns with
            # ICONIC_INCLUSION_THRESHOLD so passed quotes actually fire the boost.
            gain_db = -2.0 if seg.phrase_match_score >= 0.45 else -4.0

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

    # Deterministic ducking gate: song + detected dialogue + not song-dominant.
    has_song = bool(song_asset_id)
    has_dialogue = bool(merged)
    narrative_mode = determine_narrative_mode(content_embedding, None)
    duck_profile = _duck_profile_for(narrative_mode, content_embedding)

    with FeatureTracer("audio_ducking", gated_in=True) as duck_ft:
        ducking_enabled, ducking_reason = should_duck_audio(has_song, has_dialogue, behavior)

        if ducking_enabled:
            # Apply chosen compressor profile to every music/dialogue track so the
            # renderer has consistent sidechain parameters.
            for track in tracks:
                if track.role == "music" and not track.duck_disabled:
                    track.duck_gain_db = duck_profile["duck_gain_db"]
                    track.duck_threshold = duck_profile["threshold"]
                    track.duck_attack_ms = duck_profile["attack_ms"]
                    track.duck_release_ms = duck_profile["release_ms"]
            for track in merged:
                track.duck_threshold = duck_profile["threshold"]
                track.duck_attack_ms = duck_profile["attack_ms"]
                track.duck_release_ms = duck_profile["release_ms"]

            duck_ft.signature(
                f"applied=true,n_dialogue={len(merged)},"
                f"profile={narrative_mode},music_gain={music_policy.music_gain_db:.1f}dB,"
                f"duck_gain={duck_profile['duck_gain_db']:.1f}dB,"
                f"threshold={duck_profile['threshold']:.3f},ratio={duck_profile['ratio']}"
            )
            duck_ft.real()
        else:
            for track in tracks:
                if track.role == "music":
                    track.duck_disabled = True
                    track.duck_gain_db = 0.0
                    track.duck_threshold = 1.0
            duck_ft.fallback(f"gate:{ducking_reason}")

    if features.use_jl_cuts:
        _apply_jl_cuts(merged, cutlist.slots, clip_paths, total_duration)

    if features.use_stem_aware_audio and song_meaning is not None:
        _apply_stem_aware_ducking(tracks, song_meaning, total_duration)

    tracks.extend(merged)

    # AC1 captions: burn word-level dialogue captions into the output.
    if slot_dialogue_segments:
        caption_overlays = generate_caption_overlays_from_segments(
            slot_dialogue_segments,
            style="tiktok_white_pop",
            clip_paths=clip_paths,
        )
        if caption_overlays:
            cutlist.overlays = list(cutlist.overlays or []) + caption_overlays

    if ft is not None:
        dialogue_count = sum(1 for t in tracks if t.role == "dialogue")
        ft.signature(f"tracks={len(tracks)},dialogue={dialogue_count}")
        ft.real()
    return tracks


def _probe_duration(path: str) -> float:
    """Best-effort media duration using ffprobe."""
    try:
        import subprocess
        out = subprocess.check_output(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", path],
            stderr=subprocess.DEVNULL,
            text=True,
        )
        return float(out.strip())
    except Exception:
        return 0.0


def _apply_jl_cuts(
    dialogue_tracks: List[AudioTrack],
    slots: List[Any],
    clip_paths: Dict[str, str],
    total_duration: float,
) -> None:
    """Extend dialogue audio slightly before/after its slot video for J/L cuts.

    Lead-in/tail are clamped by neighboring slots and the source clip duration.
    """
    slot_by_index = {s.index: s for s in slots}
    sorted_slots = sorted(slots, key=lambda s: s.start_s)
    for track in dialogue_tracks:
        slot = slot_by_index.get(track.slot_index) if track.slot_index is not None else None
        if slot is None:
            continue

        lead_in = 0.25
        tail = 0.25

        # Neighbor boundaries.
        slot_start = slot.start_s
        slot_end = slot.start_s + slot.duration_s
        prev_end = 0.0
        next_start = total_duration
        for s in sorted_slots:
            if s.start_s + s.duration_s <= slot_start:
                prev_end = max(prev_end, s.start_s + s.duration_s)
            if s.start_s >= slot_end:
                next_start = min(next_start, s.start_s)
                break

        lead_in = min(lead_in, slot_start - prev_end)
        tail = min(tail, next_start - slot_end)

        # Source clip duration boundary.
        clip_path = clip_paths.get(track.asset_id)
        clip_dur = _probe_duration(clip_path) if clip_path else 0.0
        if clip_dur > 0 and track.source_start_s is not None:
            lead_in = min(lead_in, track.source_start_s)
            tail = min(tail, clip_dur - (track.source_end_s or clip_dur))

        lead_in = max(0.0, lead_in)
        tail = max(0.0, tail)

        track.j_cut_lead_in_s = round(lead_in, 3)
        track.l_cut_tail_s = round(tail, 3)
        track.start_s = round(max(0.0, track.start_s - lead_in), 3)
        track.end_s = round(min(total_duration, track.end_s + tail), 3)
        if track.source_start_s is not None:
            track.source_start_s = round(max(0.0, track.source_start_s - lead_in), 3)
        if track.source_end_s is not None:
            track.source_end_s = round(min(clip_dur or float("inf"), track.source_end_s + tail), 3)


def _vocal_arousal_at_time(t: float, song_meaning: SongMeaning, window_s: float = 1.0) -> float:
    """Compute a weighted arousal score from vocal emotion samples near ``t``."""
    samples = [
        s for s in song_meaning.vocal_emotion_curve.samples
        if abs(s.t_center_s - t) <= window_s
    ]
    if not samples:
        return 0.5
    arousal_map = {"happy": 0.8, "angry": 0.8, "excited": 0.9, "neutral": 0.4, "sad": 0.2, "fear": 0.6, "calm": 0.2}
    total = 0.0
    weight = 0.0
    for s in samples:
        for emotion, score in (s.distribution or {}).items():
            total += arousal_map.get(emotion, 0.5) * score
            weight += score
    return total / weight if weight > 0 else 0.5


def _apply_stem_aware_ducking(
    tracks: List[AudioTrack],
    song_meaning: SongMeaning,
    total_duration: float,
) -> None:
    """Disable ducking during bass drops and make ducking more aggressive during high-arousal vocals."""
    bass_drops = sorted(song_meaning.music_event_grid.bass_drop_times)
    for track in tracks:
        if track.role != "music":
            continue
        t_mid = (track.start_s + track.end_s) / 2.0
        window = 0.25
        if bass_drops and any(abs(d - t_mid) <= window for d in bass_drops):
            track.duck_disabled = True

        # High-arousal vocal section -> duck music harder.
        arousal = _vocal_arousal_at_time(t_mid, song_meaning)
        if arousal > 0.65 and not track.duck_disabled:
            track.duck_gain_db = max(-20.0, track.duck_gain_db - 2.0)
