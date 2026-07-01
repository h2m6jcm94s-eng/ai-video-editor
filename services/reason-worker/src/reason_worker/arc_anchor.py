# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
"""Map narrative arc templates to concrete song time ranges.

The mapper finds valleys and peaks in the song energy curve, snaps them to the
nearest downbeats, and uses them to anchor the arc's high-importance beats.
Lower-importance beats fill the remaining gaps.
"""

from dataclasses import dataclass
from typing import List, Optional

from shared_py.models import BeatGrid, EmotionLabel
from reason_worker.narrative_arcs import ArcTemplate, ArcBeat


@dataclass
class ArcBeatAnchor:
    """A concrete time window for one narrative beat."""

    name: str
    start_s: float
    end_s: float
    energy_target: float
    emotion_target: EmotionLabel
    preferred_shots: List[str]
    text_archetype: str

    @property
    def duration_s(self) -> float:
        return max(0.0, self.end_s - self.start_s)


def _energy_at_time(time_s: float, energy_curve: List[float], duration_s: float) -> float:
    if not energy_curve or duration_s <= 0:
        return 0.5
    progress = max(0.0, min(1.0, time_s / duration_s))
    idx = min(int(progress * len(energy_curve)), len(energy_curve) - 1)
    return energy_curve[idx]


def find_lowest_valley_in_range(
    energy_curve: List[float],
    duration_s: float,
    start_pct: float,
    end_pct: float,
) -> float:
    """Return the time (in seconds) of the lowest energy valley in a percentage range."""
    if not energy_curve:
        return duration_s * (start_pct + end_pct) / 2

    start_s = duration_s * start_pct
    end_s = duration_s * end_pct
    best_t = (start_s + end_s) / 2
    best_energy = float("inf")
    for idx, energy in enumerate(energy_curve):
        t_s = duration_s * idx / max(1, len(energy_curve) - 1)
        if t_s < start_s - 1e-6 or t_s > end_s + 1e-6:
            continue
        if energy < best_energy:
            best_energy = energy
            best_t = t_s
    return best_t


def find_climax_peak(
    energy_curve: List[float],
    duration_s: float,
    start_pct: float,
    end_pct: float,
) -> float:
    """Return the time (in seconds) of the highest energy peak in a percentage range."""
    if not energy_curve:
        return duration_s * (start_pct + end_pct) / 2

    start_s = duration_s * start_pct
    end_s = duration_s * end_pct
    best_t = (start_s + end_s) / 2
    best_energy = float("-inf")
    for idx, energy in enumerate(energy_curve):
        t_s = duration_s * idx / max(1, len(energy_curve) - 1)
        if t_s < start_s - 1e-6 or t_s > end_s + 1e-6:
            continue
        if energy > best_energy:
            best_energy = energy
            best_t = t_s
    return best_t


def nearest_downbeat(time_s: float, downbeats: List[float]) -> float:
    """Snap a time to the nearest downbeat, returning the original time if none."""
    if not downbeats:
        return time_s
    nearest = min(downbeats, key=lambda d: abs(d - time_s))
    return nearest


def _anchor_beat(
    beat: ArcBeat,
    anchor_time_s: float,
    next_anchor_time_s: Optional[float],
    prev_anchor_time_s: Optional[float],
    duration_s: float,
    downbeats: List[float],
) -> ArcBeatAnchor:
    """Build an anchored window around a target time for one arc beat."""
    start_pct = beat.position_start_pct
    end_pct = beat.position_end_pct

    # Use the template's declared window as a soft bound, but do not cross
    # neighboring anchors.
    soft_start = duration_s * start_pct
    soft_end = duration_s * end_pct

    center = nearest_downbeat(anchor_time_s, downbeats)
    half_width = (soft_end - soft_start) / 2

    if prev_anchor_time_s is not None:
        soft_start = max(soft_start, prev_anchor_time_s)
    if next_anchor_time_s is not None:
        soft_end = min(soft_end, next_anchor_time_s)

    start_s = max(soft_start, min(center - half_width, soft_end - 0.5))
    end_s = max(start_s + 0.5, min(center + half_width, soft_end))

    # Final clamp and nearest-downbeat snap for the start.
    start_s = max(0.0, min(duration_s, start_s))
    end_s = max(start_s + 0.5, min(duration_s, end_s))
    if downbeats:
        snapped_start = nearest_downbeat(start_s, downbeats)
        # Only snap backward to a downbeat if it does not cross a previous anchor.
        if snapped_start >= start_s - 0.5:
            start_s = snapped_start
        start_s = max(soft_start, start_s)

    return ArcBeatAnchor(
        name=beat.name,
        start_s=round(start_s, 3),
        end_s=round(end_s, 3),
        energy_target=beat.energy_target,
        emotion_target=beat.emotion_target,
        preferred_shots=beat.preferred_shots,
        text_archetype=beat.text_archetype,
    )


def map_arc_to_song(
    arc_template: ArcTemplate,
    energy_curve: List[float],
    beat_grid: BeatGrid,
    duration_s: float,
) -> List[ArcBeatAnchor]:
    """Map an arc template to concrete time windows on a song.

    High-importance beats (CRISIS, CLIMAX, VICTORY, GRIEF, FALL, RESOLUTION) are
    anchored to valleys or peaks and snapped to downbeats.  The remaining beats
    fill the gaps between anchored beats.
    """
    downbeats = sorted(b for b in beat_grid.downbeats if b <= duration_s)
    anchors: List[ArcBeatAnchor] = []

    # Identify which beats need hard anchors.
    valley_beats = {"CRISIS", "FALL", "RESOLUTION"}
    peak_beats = {"VICTORY", "CLIMAX", "GRIEF", "HOOK"}

    raw_times: dict = {}
    for beat in arc_template.beats:
        if beat.name in valley_beats:
            raw_times[beat.name] = find_lowest_valley_in_range(
                energy_curve, duration_s, beat.position_start_pct, beat.position_end_pct
            )
        elif beat.name in peak_beats:
            raw_times[beat.name] = find_climax_peak(
                energy_curve, duration_s, beat.position_start_pct, beat.position_end_pct
            )
        else:
            # Mid-template default: center of declared window, snapped to downbeat.
            center = duration_s * (beat.position_start_pct + beat.position_end_pct) / 2
            raw_times[beat.name] = nearest_downbeat(center, downbeats)

    # Build anchors in template order, respecting neighbors.
    prev_end: Optional[float] = 0.0
    for i, beat in enumerate(arc_template.beats):
        next_time = raw_times.get(arc_template.beats[i + 1].name) if i + 1 < len(arc_template.beats) else None
        anchor = _anchor_beat(
            beat,
            raw_times[beat.name],
            next_anchor_time_s=next_time,
            prev_anchor_time_s=prev_end,
            duration_s=duration_s,
            downbeats=downbeats,
        )
        anchors.append(anchor)
        prev_end = anchor.end_s

    return anchors


def anchor_for_time(anchors: List[ArcBeatAnchor], time_s: float) -> Optional[ArcBeatAnchor]:
    """Return the anchor whose window contains ``time_s``."""
    for anchor in anchors:
        if anchor.start_s <= time_s < anchor.end_s:
            return anchor
    # Fallback: nearest anchor by center.
    if not anchors:
        return None
    return min(
        anchors,
        key=lambda a: abs((a.start_s + a.end_s) / 2 - time_s),
    )
