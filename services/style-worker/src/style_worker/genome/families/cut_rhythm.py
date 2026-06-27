# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
# Commercial SaaS use is prohibited without written permission.
"""Cut rhythm / pacing feature family for the Style Genome."""

from __future__ import annotations

import math
from typing import Callable, List, Optional

from shared_py.models import BeatGrid, CutRhythmFamily, ShotBoundary


def _section_cut_density(
    shots: List[ShotBoundary],
    segments: List,
    label_matches: Callable[[str], bool],
) -> float:
    """Cuts per minute inside segments whose labels match ``label_matches``."""
    if not segments or len(shots) < 2:
        return 0.0

    cut_times = [s.start_s for s in shots[1:]]
    total_duration = 0.0
    matched_cuts = 0

    for segment in segments:
        if not label_matches(segment.label.lower()):
            continue
        duration = max(0.0, segment.end - segment.start)
        if duration <= 0:
            continue
        total_duration += duration
        matched_cuts += sum(1 for c in cut_times if segment.start <= c < segment.end)

    if total_duration <= 0:
        return 0.0
    return matched_cuts / (total_duration / 60.0)


def _beat_cut_alignment(
    cut_times: List[float],
    beats: List[float],
    downbeats: List[float],
    bpm: float,
) -> tuple:
    """Return (on_beat_ratio, on_downbeat_ratio, avg_nearest_beat_s)."""
    total = len(cut_times)
    if total == 0 or not beats:
        return 0.0, 0.0, 0.0

    beat_period = 60.0 / bpm if bpm > 0 else 0.5
    tolerance = beat_period / 4.0

    on_beat = 0
    on_downbeat = 0
    distances = []

    for cut in cut_times:
        nearest_beat = min(abs(cut - b) for b in beats)
        distances.append(nearest_beat)
        if nearest_beat <= tolerance:
            on_beat += 1
        if downbeats and min(abs(cut - d) for d in downbeats) <= tolerance:
            on_downbeat += 1

    avg_distance = sum(distances) / len(distances) if distances else 0.0
    on_beat_ratio = on_beat / total
    on_downbeat_ratio = on_downbeat / total

    return on_beat_ratio, on_downbeat_ratio, avg_distance


def _section_beat_ratio(
    cut_times: List[float],
    segments: List,
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


def extract_cut_rhythm(
    video_path: str,
    beat_grid: Optional[BeatGrid],
    shot_boundaries: List[ShotBoundary],
    video_info: dict,
) -> CutRhythmFamily:
    """Extract the 15 cut-rhythm features."""
    del video_path  # kept for API symmetry; frame-based work uses ``shot_boundaries``

    durations = [max(0.0, s.end_s - s.start_s) for s in shot_boundaries]
    total_cuts = max(0, len(shot_boundaries) - 1)
    n = len(durations)

    avg_duration = sum(durations) / n if n else 0.0
    std_duration = 0.0
    if n > 1:
        variance = sum((d - avg_duration) ** 2 for d in durations) / (n - 1)
        std_duration = math.sqrt(variance)
    min_duration = min(durations) if durations else 0.0
    max_duration = max(durations) if durations else 0.0

    duration_s = video_info.get("duration_s") or sum(durations)
    cut_density = total_cuts / (duration_s / 60.0) if duration_s > 0 else 0.0

    segments = beat_grid.segments if beat_grid else []

    verse_density = _section_cut_density(
        shots=shot_boundaries, segments=segments, label_matches=lambda label: "verse" in label
    )
    chorus_density = _section_cut_density(
        shots=shot_boundaries, segments=segments, label_matches=lambda label: "chorus" in label
    )
    drop_density = _section_cut_density(
        shots=shot_boundaries, segments=segments, label_matches=lambda label: "drop" in label
    )
    intro_density = _section_cut_density(
        shots=shot_boundaries, segments=segments, label_matches=lambda label: "intro" in label
    )
    outro_density = _section_cut_density(
        shots=shot_boundaries, segments=segments, label_matches=lambda label: "outro" in label
    )
    build_density = _section_cut_density(
        shots=shot_boundaries,
        segments=segments,
        label_matches=lambda label: "build" in label or "buildup" in label or "build-up" in label,
    )

    transitions = [s.transition_in for s in shot_boundaries]
    transition_count = len(transitions)
    hard_cuts = sum(1 for t in transitions if t == "hard_cut")
    gradual = sum(1 for s in shot_boundaries if s.is_gradual)
    hard_ratio = hard_cuts / transition_count if transition_count else 0.0
    gradual_ratio = gradual / transition_count if transition_count else 0.0

    cut_times = [s.start_s for s in shot_boundaries[1:]] if total_cuts else []
    if beat_grid and beat_grid.beats and cut_times:
        _on_beat, on_down, avg_dist = _beat_cut_alignment(
            cut_times=cut_times,
            beats=beat_grid.beats,
            downbeats=beat_grid.downbeats,
            bpm=beat_grid.bpm,
        )
        del _on_beat, avg_dist
    else:
        on_down = 0.0

    return CutRhythmFamily(
        total_cuts=total_cuts,
        avg_cut_duration_s=avg_duration,
        std_cut_duration_s=std_duration,
        min_cut_duration_s=min_duration,
        max_cut_duration_s=max_duration,
        cut_density_per_min=cut_density,
        verse_cut_density=verse_density,
        chorus_cut_density=chorus_density,
        drop_cut_density=drop_density,
        intro_cut_density=intro_density,
        outro_cut_density=outro_density,
        build_up_cut_density=build_density,
        hard_cut_ratio=hard_ratio,
        gradual_transition_ratio=gradual_ratio,
        cuts_on_downbeat_ratio=on_down,
        # Section-beat ratios live in the audio_align family.
    )
