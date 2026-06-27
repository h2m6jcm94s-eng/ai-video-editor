# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
# Commercial SaaS use is prohibited without written permission.
"""Audio-alignment feature family for the Style Genome."""

from __future__ import annotations

from typing import Any, Callable, List, Optional

from shared_py.models import AudioAlignFamily, BeatGrid, ShotBoundary


def _beat_tolerance(bpm: float) -> float:
    beat_period = 60.0 / bpm if bpm > 0 else 0.5
    return beat_period / 4.0


def _section_beat_ratio(
    cut_times: List[float],
    segments: List[Any],
    beats: List[float],
    tolerance: float,
    label_matches: Callable[[str], bool],
) -> float:
    """Ratio of cuts inside matching segments that land on a beat."""
    if not segments or not beats or not cut_times:
        return 0.0

    total = 0
    matched = 0
    for segment in segments:
        if not label_matches(segment.label.lower()):
            continue
        cuts_in_segment = [c for c in cut_times if segment.start <= c < segment.end]
        total += len(cuts_in_segment)
        for c in cuts_in_segment:
            if min(abs(c - b) for b in beats) <= tolerance:
                matched += 1

    return matched / total if total > 0 else 0.0


def _audio_track_metrics(audio_tracks: Optional[List[Any]]) -> tuple:
    """Derive duck frequency, dialogue ratio, and average dialogue duration."""
    if not audio_tracks:
        return 0.0, 0.0, 0.0

    music = [t for t in audio_tracks if getattr(t, "role", None) == "music"]
    dialogue = [t for t in audio_tracks if getattr(t, "role", None) in ("dialogue", "voiceover")]

    duck_freq = sum(1 for t in music if not getattr(t, "duck_disabled", False)) / len(music) if music else 0.0
    dialogue_ratio = len(dialogue) / len(audio_tracks) if audio_tracks else 0.0
    avg_dialogue = (
        sum(max(0.0, t.end_s - t.start_s) for t in dialogue) / len(dialogue) if dialogue else 0.0
    )

    return duck_freq, dialogue_ratio, avg_dialogue


def extract_audio_align_genome(
    video_path: str,
    beat_grid: Optional[BeatGrid],
    shot_boundaries: List[ShotBoundary],
    audio_tracks: Optional[List[Any]] = None,
) -> AudioAlignFamily:
    """Extract the 10 audio-alignment features."""
    del video_path  # reserved for future audio extraction; beats/shot data are sufficient here

    cut_times = [s.start_s for s in shot_boundaries[1:]] if len(shot_boundaries) > 1 else []
    total_cuts = len(cut_times)

    if beat_grid and beat_grid.beats and total_cuts:
        beats = beat_grid.beats
        downbeats = beat_grid.downbeats or []
        tolerance = _beat_tolerance(beat_grid.bpm)

        on_beat = 0
        on_downbeat = 0
        distances = []
        for c in cut_times:
            nearest_beat = min(abs(c - b) for b in beats)
            distances.append(nearest_beat)
            if nearest_beat <= tolerance:
                on_beat += 1
            if downbeats and min(abs(c - d) for d in downbeats) <= tolerance:
                on_downbeat += 1

        cut_to_beat = on_beat / total_cuts
        cut_to_downbeat = on_downbeat / total_cuts
        avg_nearest_beat = sum(distances) / len(distances) if distances else 0.0

        segments = beat_grid.segments or []
        verse_ratio = _section_beat_ratio(
            cut_times, segments, beats, tolerance, lambda label: "verse" in label
        )
        chorus_ratio = _section_beat_ratio(
            cut_times, segments, beats, tolerance, lambda label: "chorus" in label
        )
        drop_ratio = _section_beat_ratio(
            cut_times, segments, beats, tolerance, lambda label: "drop" in label
        )
    else:
        cut_to_beat = 0.0
        cut_to_downbeat = 0.0
        avg_nearest_beat = 0.0
        verse_ratio = 0.0
        chorus_ratio = 0.0
        drop_ratio = 0.0

    duck_freq, dialogue_ratio, avg_dialogue = _audio_track_metrics(audio_tracks)

    return AudioAlignFamily(
        cut_to_beat_alignment=cut_to_beat,
        cut_to_downbeat_alignment=cut_to_downbeat,
        verse_cut_to_beat_ratio=verse_ratio,
        chorus_cut_to_beat_ratio=chorus_ratio,
        drop_cut_to_beat_ratio=drop_ratio,
        avg_cut_to_nearest_beat_s=avg_nearest_beat,
        music_duck_frequency=duck_freq,
        dialogue_clip_ratio=dialogue_ratio,
        iconic_line_count=0,
        avg_dialogue_duration_s=avg_dialogue,
    )
